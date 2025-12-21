#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/autonomous_agent.py — ReAct-style Autonomous Agent for QuantumDev Max

Implements a ReAct (Reason + Act) loop for autonomous multi-step task execution.

Features:
- Goal decomposition into executable steps
- LLM-driven planning and tool selection
- Self-correction and retry logic
- Parallel execution of independent steps
- Reasoning trace transparency
- User approval workflow (optional)

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

from __future__ import annotations

import os
import re
import json
import time
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable, Awaitable, Union
from dataclasses import dataclass, field
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


# === Configuration ===
def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        m = re.search(r"-?\d+", raw)
        return int(m.group(0)) if m else default
    except Exception:
        return default


# Environment configuration
ENABLE_AUTONOMOUS_MODE = _env_bool("ENABLE_AUTONOMOUS_MODE", True)
AUTONOMOUS_MAX_STEPS = _env_int("AUTONOMOUS_MAX_STEPS", 10)
AUTONOMOUS_MAX_RETRIES = _env_int("AUTONOMOUS_MAX_RETRIES", 3)
AUTONOMOUS_REQUIRE_APPROVAL = _env_bool("AUTONOMOUS_REQUIRE_APPROVAL", False)
AUTONOMOUS_MAX_PARALLEL_TOOLS = _env_int("AUTONOMOUS_MAX_PARALLEL_TOOLS", 5)


# === Enums ===
class AgentStatus(str, Enum):
    """Status of the autonomous agent."""
    IDLE = "idle"
    PLANNING = "planning"
    AWAITING_APPROVAL = "awaiting_approval"
    EXECUTING = "executing"
    REFLECTING = "reflecting"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class StepDecision(str, Enum):
    """Decision after step reflection."""
    CONTINUE = "continue"
    RETRY = "retry"
    REPLAN = "replan"
    ABORT = "abort"
    COMPLETE = "complete"


# === Data Classes ===
@dataclass
class PlanStep:
    """
    Single step in an execution plan.
    
    Attributes:
        id: Unique step identifier
        tool: Tool name to execute
        args: Arguments for the tool
        description: Human-readable description
        depends_on: List of step IDs this step depends on
        parallel_group: Group ID for parallel execution
    """
    id: str
    tool: str
    args: Dict[str, Any]
    description: str
    depends_on: List[str] = field(default_factory=list)
    parallel_group: Optional[int] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "tool": self.tool,
            "args": self.args,
            "description": self.description,
            "depends_on": self.depends_on,
            "parallel_group": self.parallel_group,
        }
    
    def to_string(self) -> str:
        """Convert to string representation for display."""
        args_str = ", ".join([f"{k}={repr(v)}" for k, v in self.args.items()])
        return f"{self.tool}({args_str})"


@dataclass
class ExecutionPlan:
    """
    Complete execution plan for a goal.
    
    Attributes:
        goal: Original user goal
        steps: List of planned steps
        reasoning: LLM's reasoning for the plan
        estimated_duration_s: Estimated execution time
        requires_confirmation: Whether user confirmation is needed
    """
    goal: str
    steps: List[PlanStep]
    reasoning: str = ""
    estimated_duration_s: int = 0
    requires_confirmation: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "steps": [s.to_dict() for s in self.steps],
            "reasoning": self.reasoning,
            "estimated_duration_s": self.estimated_duration_s,
            "requires_confirmation": self.requires_confirmation,
        }
    
    def format_for_approval(self) -> str:
        """Format plan for user approval display."""
        lines = [
            f"🎯 **GOAL**: {self.goal}",
            "",
            "📋 **PLAN**:",
        ]
        
        for i, step in enumerate(self.steps, 1):
            deps_str = f" (after: {', '.join(step.depends_on)})" if step.depends_on else ""
            lines.append(f"  {i}. {step.description}{deps_str}")
            lines.append(f"     → {step.to_string()}")
        
        if self.reasoning:
            lines.extend(["", f"💭 **REASONING**: {self.reasoning}"])
        
        return "\n".join(lines)


@dataclass
class StepResult:
    """Result of executing a single step."""
    step_id: str
    success: bool
    result: Any = None
    error: Optional[str] = None
    duration_ms: int = 0
    retries: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "step_id": self.step_id,
            "success": self.success,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "retries": self.retries,
        }


@dataclass
class AgentResult:
    """Final result from the autonomous agent."""
    goal: str
    status: AgentStatus
    plan: Optional[ExecutionPlan] = None
    step_results: List[StepResult] = field(default_factory=list)
    final_response: str = ""
    total_duration_ms: int = 0
    reasoning_trace: List[Dict[str, Any]] = field(default_factory=list)
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "goal": self.goal,
            "status": self.status.value,
            "plan": self.plan.to_dict() if self.plan else None,
            "step_results": [sr.to_dict() for sr in self.step_results],
            "final_response": self.final_response,
            "total_duration_ms": self.total_duration_ms,
            "reasoning_trace": self.reasoning_trace,
            "error": self.error,
        }


# === Autonomous Agent ===
class AutonomousAgent:
    """
    ReAct-style autonomous agent that plans and executes multi-step tasks.
    
    The agent follows a Reason → Act → Observe cycle:
    1. REASON: Generate a plan to achieve the goal
    2. ACT: Execute each step using available tools
    3. OBSERVE: Reflect on results and decide next action
    
    Features:
    - LLM-driven planning and reflection
    - Parallel execution of independent steps
    - Self-correction on failures (up to 3 retries)
    - User approval workflow (optional)
    - Full reasoning trace for transparency
    """
    
    def __init__(
        self,
        llm_func: Optional[Callable[..., Awaitable[str]]] = None,
        tool_registry: Optional[Any] = None,
        require_approval: bool = AUTONOMOUS_REQUIRE_APPROVAL,
        max_steps: int = AUTONOMOUS_MAX_STEPS,
        max_retries: int = AUTONOMOUS_MAX_RETRIES,
    ):
        """
        Initialize the Autonomous Agent.
        
        Args:
            llm_func: Async function for LLM calls (prompt, system) -> response
            tool_registry: AutonomousToolRegistry instance
            require_approval: Whether to require user approval before execution
            max_steps: Maximum steps per plan
            max_retries: Maximum retries per step
        """
        self.llm_func = llm_func
        self.tool_registry = tool_registry
        self.require_approval = require_approval
        self.max_steps = max_steps
        self.max_retries = max_retries
        
        self.status = AgentStatus.IDLE
        self._current_plan: Optional[ExecutionPlan] = None
        self._step_results: Dict[str, StepResult] = {}
        self._reasoning_trace: List[Dict[str, Any]] = []
        self._abort_requested = False
        
        # Lazy load tool registry if not provided
        if self.tool_registry is None:
            try:
                from core.tool_registry import get_autonomous_tool_registry
                self.tool_registry = get_autonomous_tool_registry()
            except ImportError:
                log.warning("Tool registry not available")
    
    def abort(self) -> None:
        """Request abort of current execution."""
        self._abort_requested = True
        self.status = AgentStatus.ABORTED
        log.info("Abort requested for autonomous agent")
    
    def _add_trace(self, step_type: str, content: str, metadata: Optional[Dict] = None) -> None:
        """Add an entry to the reasoning trace."""
        self._reasoning_trace.append({
            "type": step_type,
            "content": content,
            "timestamp": int(time.time()),
            "metadata": metadata or {},
        })
    
    async def run(
        self,
        goal: str,
        approval_callback: Optional[Callable[[ExecutionPlan], Awaitable[bool]]] = None,
    ) -> AgentResult:
        """
        Run the autonomous agent to achieve a goal.
        
        Args:
            goal: The user's goal/task to accomplish
            approval_callback: Optional async callback for plan approval
            
        Returns:
            AgentResult with execution details
        """
        if not ENABLE_AUTONOMOUS_MODE:
            return AgentResult(
                goal=goal,
                status=AgentStatus.FAILED,
                error="Autonomous mode is disabled",
            )
        
        start_time = time.perf_counter()
        self.status = AgentStatus.PLANNING
        self._abort_requested = False
        self._reasoning_trace = []
        self._step_results = {}
        
        self._add_trace("start", f"Starting autonomous execution for goal: {goal}")
        
        try:
            # === STEP 1: PLAN ===
            self._add_trace("planning", "Generating execution plan...")
            plan = await self.generate_plan(goal)
            
            if not plan or not plan.steps:
                self._add_trace("error", "Failed to generate a valid plan")
                return AgentResult(
                    goal=goal,
                    status=AgentStatus.FAILED,
                    error="Failed to generate execution plan",
                    reasoning_trace=self._reasoning_trace,
                    total_duration_ms=int((time.perf_counter() - start_time) * 1000),
                )
            
            self._current_plan = plan
            self._add_trace("plan_created", plan.format_for_approval())
            
            # === STEP 2: APPROVAL (if required) ===
            if self.require_approval or plan.requires_confirmation:
                self.status = AgentStatus.AWAITING_APPROVAL
                self._add_trace("awaiting_approval", "Waiting for user approval...")
                
                if approval_callback:
                    approved = await approval_callback(plan)
                    if not approved:
                        self._add_trace("rejected", "User rejected the plan")
                        return AgentResult(
                            goal=goal,
                            status=AgentStatus.ABORTED,
                            plan=plan,
                            reasoning_trace=self._reasoning_trace,
                            total_duration_ms=int((time.perf_counter() - start_time) * 1000),
                        )
                    self._add_trace("approved", "User approved the plan")
                else:
                    # No callback provided, skip approval
                    self._add_trace("auto_approved", "No approval callback, auto-approving")
            
            # === STEP 3: EXECUTE ===
            self.status = AgentStatus.EXECUTING
            self._add_trace("executing", f"Executing plan with {len(plan.steps)} steps...")
            
            step_results = await self.execute_plan(plan)
            
            # Check for abort
            if self._abort_requested:
                return AgentResult(
                    goal=goal,
                    status=AgentStatus.ABORTED,
                    plan=plan,
                    step_results=step_results,
                    reasoning_trace=self._reasoning_trace,
                    total_duration_ms=int((time.perf_counter() - start_time) * 1000),
                )
            
            # === STEP 4: SYNTHESIZE ===
            self._add_trace("synthesizing", "Generating final response...")
            final_response = await self._synthesize_response(goal, plan, step_results)
            
            # Determine final status
            all_succeeded = all(sr.success for sr in step_results)
            final_status = AgentStatus.COMPLETED if all_succeeded else AgentStatus.FAILED
            
            self.status = final_status
            self._add_trace("completed", f"Execution completed with status: {final_status.value}")
            
            return AgentResult(
                goal=goal,
                status=final_status,
                plan=plan,
                step_results=step_results,
                final_response=final_response,
                reasoning_trace=self._reasoning_trace,
                total_duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
            
        except Exception as e:
            log.error(f"Autonomous agent error: {e}", exc_info=True)
            self.status = AgentStatus.FAILED
            self._add_trace("error", f"Execution failed: {str(e)}")
            
            return AgentResult(
                goal=goal,
                status=AgentStatus.FAILED,
                plan=self._current_plan,
                step_results=list(self._step_results.values()),
                reasoning_trace=self._reasoning_trace,
                error=str(e),
                total_duration_ms=int((time.perf_counter() - start_time) * 1000),
            )
    
    async def generate_plan(self, goal: str) -> Optional[ExecutionPlan]:
        """
        Generate an execution plan for a goal.
        
        Uses LLM to break down the goal into executable steps.
        
        Args:
            goal: User's goal to accomplish
            
        Returns:
            ExecutionPlan or None if planning fails
        """
        if not self.llm_func:
            log.error("LLM function not configured")
            return None
        
        if not self.tool_registry:
            log.error("Tool registry not configured")
            return None
        
        # Get available tools
        tools_desc = self.tool_registry.get_tool_for_planning()
        tool_names = self.tool_registry.get_tool_names()
        
        prompt = f"""You are an autonomous AI agent. Create a step-by-step plan to achieve the user's goal.

GOAL: {goal}

AVAILABLE TOOLS:
{tools_desc}

INSTRUCTIONS:
1. Break down the goal into concrete, executable steps
2. Each step must use ONE tool from the available list
3. Identify which steps can run in parallel (no dependencies between them)
4. Order steps so that dependencies are satisfied
5. Maximum {self.max_steps} steps allowed

RESPOND WITH JSON ONLY:
{{
    "reasoning": "Brief explanation of your approach",
    "steps": [
        {{
            "id": "step_1",
            "tool": "EXACT_TOOL_NAME_FROM_LIST",
            "args": {{"param1": "value1"}},
            "description": "What this step does",
            "depends_on": [],
            "parallel_group": 1
        }}
    ],
    "estimated_duration_s": 30
}}

IMPORTANT:
- Use ONLY tool names from the list: {', '.join(tool_names)}
- Steps with same parallel_group number will run in parallel
- depends_on should list step IDs that must complete first

JSON:"""
        
        system = (
            "You are a planning agent. Generate valid JSON plans using ONLY the exact tool names provided. "
            "Do not invent tool names. Be precise and minimal."
        )
        
        try:
            response = await self.llm_func(prompt, system)
            
            # Parse JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                log.warning("No JSON found in planning response")
                return None
            
            plan_data = json.loads(json_match.group())
            
            # Validate and build plan
            steps = []
            for step_data in plan_data.get("steps", []):
                tool_name = step_data.get("tool", "")
                
                # Validate tool exists
                if tool_name not in tool_names:
                    log.warning(f"Invalid tool name in plan: {tool_name}")
                    continue
                
                steps.append(PlanStep(
                    id=step_data.get("id", f"step_{len(steps)+1}"),
                    tool=tool_name,
                    args=step_data.get("args", {}),
                    description=step_data.get("description", ""),
                    depends_on=step_data.get("depends_on", []),
                    parallel_group=step_data.get("parallel_group"),
                ))
            
            if not steps:
                log.warning("No valid steps in plan")
                return None
            
            # Check if any step requires confirmation
            requires_confirmation = any(
                self.tool_registry.get(s.tool).requires_confirmation
                for s in steps
                if self.tool_registry.get(s.tool)
            )
            
            return ExecutionPlan(
                goal=goal,
                steps=steps,
                reasoning=plan_data.get("reasoning", ""),
                estimated_duration_s=plan_data.get("estimated_duration_s", 30),
                requires_confirmation=requires_confirmation,
            )
            
        except Exception as e:
            log.error(f"Plan generation failed: {e}")
            return None
    
    async def execute_plan(self, plan: ExecutionPlan) -> List[StepResult]:
        """
        Execute an execution plan.
        
        Handles parallel execution and dependencies.
        
        Args:
            plan: The ExecutionPlan to execute
            
        Returns:
            List of StepResult for each step
        """
        from core.execution_graph import ExecutionGraph, GraphExecutor
        
        # Build execution graph
        graph = ExecutionGraph()
        
        for step in plan.steps:
            graph.add_tool_step(
                tool_name=step.tool,
                arguments=step.args,
                dependencies=step.depends_on,
                step_id=step.id,
            )
        
        # Execute graph
        executor = GraphExecutor(
            tool_registry=self.tool_registry,
            max_parallel=AUTONOMOUS_MAX_PARALLEL_TOOLS,
        )
        
        exec_result = await executor.execute_graph(graph)
        
        # Convert to StepResults with reflection
        step_results = []
        
        for exec_step in exec_result.steps:
            step_result = StepResult(
                step_id=exec_step.id,
                success=exec_step.status.value == "completed",
                result=exec_step.result,
                error=exec_step.error,
                duration_ms=exec_step.duration_ms,
            )
            
            # Reflect on result and potentially retry
            if not step_result.success and step_result.retries < self.max_retries:
                self._add_trace(
                    "reflecting",
                    f"Step {exec_step.id} failed, reflecting on error..."
                )
                
                decision = await self.reflect_on_result(
                    step=next((s for s in plan.steps if s.id == exec_step.id), None),
                    result=step_result,
                )
                
                if decision == StepDecision.RETRY:
                    self._add_trace("retry", f"Retrying step {exec_step.id}...")
                    retry_result = await self._retry_step(
                        step=next((s for s in plan.steps if s.id == exec_step.id), None),
                        previous_error=exec_step.error,
                    )
                    if retry_result:
                        step_result = retry_result
            
            step_results.append(step_result)
            self._step_results[exec_step.id] = step_result
            
            self._add_trace(
                "step_completed",
                f"Step {exec_step.id}: {'✓' if step_result.success else '✗'} "
                f"({step_result.duration_ms}ms)",
                {"result_preview": str(step_result.result)[:200] if step_result.result else None}
            )
        
        return step_results
    
    async def reflect_on_result(
        self,
        step: Optional[PlanStep],
        result: StepResult,
    ) -> StepDecision:
        """
        Reflect on a step result to decide next action.
        
        Uses LLM for self-evaluation when a step fails.
        
        Args:
            step: The PlanStep that was executed
            result: The StepResult from execution
            
        Returns:
            StepDecision indicating what to do next
        """
        if result.success:
            return StepDecision.CONTINUE
        
        if not self.llm_func or not step:
            # Default: retry if under limit
            if result.retries < self.max_retries:
                return StepDecision.RETRY
            return StepDecision.ABORT
        
        prompt = f"""A step in my execution plan failed. Analyze the failure and decide what to do.

STEP: {step.to_string()}
DESCRIPTION: {step.description}
ERROR: {result.error}
RETRIES SO FAR: {result.retries}/{self.max_retries}

OPTIONS:
1. RETRY - Try the same step again (maybe transient error)
2. REPLAN - The approach is wrong, need different steps
3. ABORT - Cannot proceed, need user input
4. CONTINUE - Skip this step and continue with remaining steps

RESPOND WITH JSON:
{{
    "analysis": "What went wrong",
    "decision": "RETRY|REPLAN|ABORT|CONTINUE",
    "reason": "Why this decision",
    "suggestion": "If REPLAN, suggest alternative approach"
}}

JSON:"""
        
        try:
            response = await self.llm_func(prompt, "You are a self-reflection agent. Analyze failures concisely.")
            
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                decision_str = data.get("decision", "RETRY").upper()
                
                self._add_trace("reflection", data.get("analysis", ""), {
                    "decision": decision_str,
                    "reason": data.get("reason"),
                })
                
                if decision_str == "RETRY" and result.retries < self.max_retries:
                    return StepDecision.RETRY
                elif decision_str == "REPLAN":
                    return StepDecision.REPLAN
                elif decision_str == "CONTINUE":
                    return StepDecision.CONTINUE
                else:
                    return StepDecision.ABORT
                    
        except Exception as e:
            log.warning(f"Reflection failed: {e}")
        
        # Default fallback
        if result.retries < self.max_retries:
            return StepDecision.RETRY
        return StepDecision.ABORT
    
    async def _retry_step(
        self,
        step: Optional[PlanStep],
        previous_error: Optional[str],
    ) -> Optional[StepResult]:
        """Retry a failed step."""
        if not step or not self.tool_registry:
            return None
        
        tool = self.tool_registry.get(step.tool)
        if not tool:
            return None
        
        start_time = time.perf_counter()
        
        try:
            result = await asyncio.wait_for(
                tool.handler(**step.args),
                timeout=tool.timeout_s,
            )
            
            return StepResult(
                step_id=step.id,
                success=True,
                result=result,
                duration_ms=int((time.perf_counter() - start_time) * 1000),
                retries=1,
            )
            
        except Exception as e:
            return StepResult(
                step_id=step.id,
                success=False,
                error=str(e),
                duration_ms=int((time.perf_counter() - start_time) * 1000),
                retries=1,
            )
    
    async def _synthesize_response(
        self,
        goal: str,
        plan: ExecutionPlan,
        step_results: List[StepResult],
    ) -> str:
        """Synthesize a final response from all step results."""
        if not self.llm_func:
            # Basic synthesis without LLM
            successful = [sr for sr in step_results if sr.success]
            if not successful:
                return "Unable to complete the goal. All steps failed."
            
            results_summary = "\n".join([
                f"- {sr.step_id}: {str(sr.result)[:200]}"
                for sr in successful
            ])
            return f"Completed {len(successful)}/{len(step_results)} steps:\n{results_summary}"
        
        # Build context from results
        results_context = []
        for sr in step_results:
            step = next((s for s in plan.steps if s.id == sr.step_id), None)
            if step:
                results_context.append({
                    "step": step.description,
                    "tool": step.tool,
                    "success": sr.success,
                    "result": sr.result if sr.success else sr.error,
                })
        
        prompt = f"""I executed a multi-step plan to achieve a goal. Synthesize a comprehensive response.

GOAL: {goal}

EXECUTION RESULTS:
{json.dumps(results_context, indent=2, ensure_ascii=False, default=str)}

INSTRUCTIONS:
1. Summarize what was accomplished
2. Present the key findings/data
3. If some steps failed, acknowledge and explain impact
4. Provide a clear, actionable response to the original goal

RESPONSE:"""
        
        try:
            response = await self.llm_func(
                prompt,
                "You are an assistant synthesizing multi-step execution results. Be concise and informative."
            )
            return response
            
        except Exception as e:
            log.error(f"Synthesis failed: {e}")
            return f"Execution completed but synthesis failed: {e}"


# === Singleton Instance ===
_agent_instance: Optional[AutonomousAgent] = None


def get_autonomous_agent(
    llm_func: Optional[Callable] = None,
    tool_registry: Optional[Any] = None,
) -> AutonomousAgent:
    """
    Get or create AutonomousAgent singleton.
    
    Args:
        llm_func: LLM function for planning and reflection
        tool_registry: Tool registry instance
        
    Returns:
        AutonomousAgent instance
    """
    global _agent_instance
    
    if _agent_instance is None:
        _agent_instance = AutonomousAgent(
            llm_func=llm_func,
            tool_registry=tool_registry,
        )
    elif llm_func and _agent_instance.llm_func is None:
        _agent_instance.llm_func = llm_func
    
    return _agent_instance


# === Test ===
if __name__ == "__main__":
    import asyncio
    
    async def mock_llm(prompt: str, system: str = "") -> str:
        """Mock LLM for testing."""
        if "create a step-by-step plan" in prompt.lower():
            return json.dumps({
                "reasoning": "To compare GPU prices, we need to search for each GPU's price",
                "steps": [
                    {
                        "id": "step_1",
                        "tool": "web_search",
                        "args": {"query": "RTX 4090 price"},
                        "description": "Search for RTX 4090 prices",
                        "depends_on": [],
                        "parallel_group": 1
                    },
                    {
                        "id": "step_2",
                        "tool": "web_search",
                        "args": {"query": "RTX 4080 price"},
                        "description": "Search for RTX 4080 prices",
                        "depends_on": [],
                        "parallel_group": 1
                    }
                ],
                "estimated_duration_s": 20
            })
        elif "synthesize" in prompt.lower():
            return "Based on my research, the RTX 4090 costs approximately $1,599 while the RTX 4080 costs around $1,199."
        else:
            return '{"decision": "CONTINUE", "analysis": "Step completed"}'
    
    async def test():
        print("🧪 Testing Autonomous Agent")
        print("=" * 60)
        
        agent = AutonomousAgent(llm_func=mock_llm)
        
        # Test plan generation
        print("\n1. Testing plan generation...")
        plan = await agent.generate_plan("Compare prices of RTX 4090 and RTX 4080")
        
        if plan:
            print(f"Plan created with {len(plan.steps)} steps:")
            print(plan.format_for_approval())
        else:
            print("Plan generation failed!")
        
        print("\n✅ All tests passed!")
    
    asyncio.run(test())
