#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/execution_graph.py — DAG-based Execution Graph for Autonomous Agent

Provides:
- Dependency graph construction from execution plans
- Parallel execution of independent steps
- Topological sort for execution order
- Result aggregation and caching

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

from __future__ import annotations

import os
import re
import asyncio
import logging
import time
import hashlib
from typing import Dict, Any, Optional, List, Set, Tuple, Callable, Awaitable
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)


# === Configuration ===
def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        m = re.search(r"-?\d+", raw)
        return int(m.group(0)) if m else default
    except Exception:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


AUTONOMOUS_MAX_PARALLEL_TOOLS = _env_int("AUTONOMOUS_MAX_PARALLEL_TOOLS", 5)
AUTONOMOUS_MAX_STEPS = _env_int("AUTONOMOUS_MAX_STEPS", 10)


# === Enums ===
class StepStatus(str, Enum):
    """Execution status of a step."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class StepType(str, Enum):
    """Type of execution step."""
    TOOL_CALL = "tool_call"
    CONDITION = "condition"
    AGGREGATION = "aggregation"
    SYNTHESIS = "synthesis"


# === Data Classes ===
@dataclass
class ExecutionStep:
    """
    Single step in the execution graph.
    
    Attributes:
        id: Unique step identifier
        step_type: Type of step (tool_call, condition, etc.)
        tool_name: Name of the tool to execute (for tool_call steps)
        arguments: Arguments to pass to the tool
        dependencies: List of step IDs this step depends on
        status: Current execution status
        result: Execution result
        error: Error message if failed
        duration_ms: Execution duration in milliseconds
        metadata: Additional metadata
    """
    id: str
    step_type: StepType
    tool_name: Optional[str] = None
    arguments: Dict[str, Any] = field(default_factory=dict)
    dependencies: List[str] = field(default_factory=list)
    status: StepStatus = StepStatus.PENDING
    result: Any = None
    error: Optional[str] = None
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "step_type": self.step_type.value,
            "tool_name": self.tool_name,
            "arguments": self.arguments,
            "dependencies": self.dependencies,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
        }


@dataclass
class ExecutionResult:
    """Result of executing the entire graph."""
    success: bool
    steps: List[ExecutionStep]
    final_result: Any = None
    total_duration_ms: int = 0
    parallel_groups_executed: int = 0
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "steps": [s.to_dict() for s in self.steps],
            "final_result": self.final_result,
            "total_duration_ms": self.total_duration_ms,
            "parallel_groups_executed": self.parallel_groups_executed,
            "error": self.error,
        }


# === Execution Graph ===
class ExecutionGraph:
    """
    Directed Acyclic Graph (DAG) for managing step execution.
    
    Features:
    - Automatic dependency detection
    - Parallel execution of independent steps
    - Topological sort for execution order
    - Result caching for retry scenarios
    """
    
    def __init__(self):
        self.steps: Dict[str, ExecutionStep] = {}
        self._adjacency: Dict[str, List[str]] = defaultdict(list)  # step -> dependents
        self._reverse_adjacency: Dict[str, List[str]] = defaultdict(list)  # step -> dependencies
        self._result_cache: Dict[str, Any] = {}
        self._step_counter = 0
    
    def add_step(
        self,
        step_type: StepType,
        tool_name: Optional[str] = None,
        arguments: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
        step_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionStep:
        """
        Add a step to the execution graph.
        
        Args:
            step_type: Type of step
            tool_name: Tool to execute (for tool_call steps)
            arguments: Tool arguments
            dependencies: List of step IDs this step depends on
            step_id: Custom step ID (auto-generated if not provided)
            metadata: Additional metadata
            
        Returns:
            The created ExecutionStep
        """
        if step_id is None:
            self._step_counter += 1
            step_id = f"step_{self._step_counter}"
        
        step = ExecutionStep(
            id=step_id,
            step_type=step_type,
            tool_name=tool_name,
            arguments=arguments or {},
            dependencies=dependencies or [],
            metadata=metadata or {},
        )
        
        self.steps[step_id] = step
        
        # Update adjacency lists
        for dep in step.dependencies:
            self._adjacency[dep].append(step_id)
            self._reverse_adjacency[step_id].append(dep)
        
        return step
    
    def add_tool_step(
        self,
        tool_name: str,
        arguments: Optional[Dict[str, Any]] = None,
        dependencies: Optional[List[str]] = None,
        step_id: Optional[str] = None,
    ) -> ExecutionStep:
        """Convenience method to add a tool execution step."""
        return self.add_step(
            step_type=StepType.TOOL_CALL,
            tool_name=tool_name,
            arguments=arguments,
            dependencies=dependencies,
            step_id=step_id,
        )
    
    def add_aggregation_step(
        self,
        dependencies: List[str],
        step_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ExecutionStep:
        """Add an aggregation step that combines results from multiple steps."""
        return self.add_step(
            step_type=StepType.AGGREGATION,
            dependencies=dependencies,
            step_id=step_id,
            metadata=metadata or {"operation": "aggregate"},
        )
    
    def detect_parallelizable_groups(self) -> List[List[str]]:
        """
        Detect groups of steps that can be executed in parallel.
        
        Uses topological sort to identify steps at the same "level"
        that have no dependencies on each other.
        
        Returns:
            List of groups, where each group contains step IDs that can run in parallel
        """
        # Compute in-degree for each step
        in_degree: Dict[str, int] = {step_id: 0 for step_id in self.steps}
        for step_id, deps in self._reverse_adjacency.items():
            in_degree[step_id] = len(deps)
        
        # Group steps by their level in the DAG
        groups: List[List[str]] = []
        remaining = set(self.steps.keys())
        
        while remaining:
            # Find all steps with no remaining dependencies
            ready = [
                step_id for step_id in remaining
                if all(dep not in remaining for dep in self._reverse_adjacency.get(step_id, []))
            ]
            
            if not ready:
                # Cycle detected or no progress - break
                log.warning("Cycle detected in execution graph or no progress made")
                break
            
            groups.append(ready)
            remaining -= set(ready)
        
        return groups
    
    def get_execution_order(self) -> List[str]:
        """
        Get the topological execution order of all steps.
        
        Returns:
            List of step IDs in execution order
        """
        groups = self.detect_parallelizable_groups()
        return [step_id for group in groups for step_id in group]
    
    def get_ready_steps(self) -> List[str]:
        """
        Get steps that are ready to execute (all dependencies completed).
        
        Returns:
            List of step IDs ready to execute
        """
        ready = []
        for step_id, step in self.steps.items():
            if step.status != StepStatus.PENDING:
                continue
            
            deps_completed = all(
                self.steps.get(dep, ExecutionStep(id=dep, step_type=StepType.TOOL_CALL)).status
                == StepStatus.COMPLETED
                for dep in step.dependencies
            )
            
            if deps_completed:
                ready.append(step_id)
        
        return ready
    
    def mark_step_completed(
        self,
        step_id: str,
        result: Any,
        duration_ms: int = 0,
    ) -> None:
        """Mark a step as completed with its result."""
        if step_id in self.steps:
            step = self.steps[step_id]
            step.status = StepStatus.COMPLETED
            step.result = result
            step.duration_ms = duration_ms
            self._result_cache[step_id] = result
    
    def mark_step_failed(
        self,
        step_id: str,
        error: str,
        duration_ms: int = 0,
    ) -> None:
        """Mark a step as failed with an error."""
        if step_id in self.steps:
            step = self.steps[step_id]
            step.status = StepStatus.FAILED
            step.error = error
            step.duration_ms = duration_ms
    
    def get_step_result(self, step_id: str) -> Any:
        """Get the cached result of a completed step."""
        return self._result_cache.get(step_id)
    
    def get_dependency_results(self, step_id: str) -> Dict[str, Any]:
        """Get results from all dependencies of a step."""
        step = self.steps.get(step_id)
        if not step:
            return {}
        
        return {
            dep: self._result_cache.get(dep)
            for dep in step.dependencies
            if dep in self._result_cache
        }
    
    def validate(self) -> Tuple[bool, Optional[str]]:
        """
        Validate the execution graph.
        
        Checks for:
        - Cycles
        - Missing dependencies
        - Step limit
        
        Returns:
            Tuple of (is_valid, error_message)
        """
        # Check step limit
        if len(self.steps) > AUTONOMOUS_MAX_STEPS:
            return False, f"Too many steps: {len(self.steps)} > {AUTONOMOUS_MAX_STEPS}"
        
        # Check for missing dependencies
        for step_id, step in self.steps.items():
            for dep in step.dependencies:
                if dep not in self.steps:
                    return False, f"Step '{step_id}' has missing dependency: '{dep}'"
        
        # Check for cycles using DFS
        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        
        def has_cycle(node: str) -> bool:
            visited.add(node)
            rec_stack.add(node)
            
            for neighbor in self._adjacency.get(node, []):
                if neighbor not in visited:
                    if has_cycle(neighbor):
                        return True
                elif neighbor in rec_stack:
                    return True
            
            rec_stack.remove(node)
            return False
        
        for step_id in self.steps:
            if step_id not in visited:
                if has_cycle(step_id):
                    return False, "Cycle detected in execution graph"
        
        return True, None
    
    def to_dict(self) -> Dict[str, Any]:
        """Serialize the graph to a dictionary."""
        return {
            "steps": {step_id: step.to_dict() for step_id, step in self.steps.items()},
            "parallel_groups": self.detect_parallelizable_groups(),
            "execution_order": self.get_execution_order(),
        }


# === Graph Executor ===
class GraphExecutor:
    """
    Executes an ExecutionGraph with parallel execution support.
    """
    
    def __init__(
        self,
        tool_registry: Optional[Any] = None,
        max_parallel: int = AUTONOMOUS_MAX_PARALLEL_TOOLS,
    ):
        """
        Initialize the executor.
        
        Args:
            tool_registry: AutonomousToolRegistry instance
            max_parallel: Maximum parallel tool executions
        """
        self.tool_registry = tool_registry
        self.max_parallel = max_parallel
        self._semaphore: Optional[asyncio.Semaphore] = None
    
    async def execute_graph(
        self,
        graph: ExecutionGraph,
        aggregator: Optional[Callable[[Dict[str, Any]], Awaitable[Any]]] = None,
    ) -> ExecutionResult:
        """
        Execute the entire graph.
        
        Args:
            graph: The ExecutionGraph to execute
            aggregator: Optional async function to aggregate final results
            
        Returns:
            ExecutionResult with all step results
        """
        start_time = time.perf_counter()
        
        # Validate graph
        is_valid, error = graph.validate()
        if not is_valid:
            return ExecutionResult(
                success=False,
                steps=list(graph.steps.values()),
                error=error,
            )
        
        # Initialize semaphore for parallel execution limiting
        self._semaphore = asyncio.Semaphore(self.max_parallel)
        
        # Get parallel groups
        groups = graph.detect_parallelizable_groups()
        parallel_groups_executed = 0
        
        try:
            for group in groups:
                # Execute all steps in this group in parallel
                tasks = [
                    self._execute_step_with_limit(graph, step_id)
                    for step_id in group
                    if graph.steps[step_id].status == StepStatus.PENDING
                ]
                
                if tasks:
                    await asyncio.gather(*tasks, return_exceptions=True)
                    parallel_groups_executed += 1
                
                # Check if any critical step failed
                for step_id in group:
                    step = graph.steps[step_id]
                    if step.status == StepStatus.FAILED:
                        # Check if this failure blocks downstream steps
                        dependents = graph._adjacency.get(step_id, [])
                        for dep_id in dependents:
                            graph.steps[dep_id].status = StepStatus.SKIPPED
                            graph.steps[dep_id].error = f"Skipped due to failed dependency: {step_id}"
        
        except Exception as e:
            log.error(f"Graph execution error: {e}", exc_info=True)
            return ExecutionResult(
                success=False,
                steps=list(graph.steps.values()),
                error=str(e),
                total_duration_ms=int((time.perf_counter() - start_time) * 1000),
                parallel_groups_executed=parallel_groups_executed,
            )
        
        # Determine final result
        final_result = None
        all_completed = all(
            s.status == StepStatus.COMPLETED
            for s in graph.steps.values()
        )
        
        if all_completed:
            # Aggregate results if aggregator provided
            if aggregator:
                try:
                    all_results = {
                        step_id: step.result
                        for step_id, step in graph.steps.items()
                    }
                    final_result = await aggregator(all_results)
                except Exception as e:
                    log.error(f"Result aggregation error: {e}")
            else:
                # Return all results
                final_result = {
                    step_id: step.result
                    for step_id, step in graph.steps.items()
                }
        
        total_duration = int((time.perf_counter() - start_time) * 1000)
        
        return ExecutionResult(
            success=all_completed,
            steps=list(graph.steps.values()),
            final_result=final_result,
            total_duration_ms=total_duration,
            parallel_groups_executed=parallel_groups_executed,
        )
    
    async def _execute_step_with_limit(
        self,
        graph: ExecutionGraph,
        step_id: str,
    ) -> None:
        """Execute a single step with semaphore limiting."""
        async with self._semaphore:
            await self._execute_step(graph, step_id)
    
    async def _execute_step(
        self,
        graph: ExecutionGraph,
        step_id: str,
    ) -> None:
        """Execute a single step."""
        step = graph.steps.get(step_id)
        if not step:
            return
        
        step.status = StepStatus.RUNNING
        start_time = time.perf_counter()
        
        try:
            if step.step_type == StepType.TOOL_CALL:
                result = await self._execute_tool(step, graph)
            elif step.step_type == StepType.AGGREGATION:
                result = self._aggregate_results(step, graph)
            elif step.step_type == StepType.CONDITION:
                result = await self._evaluate_condition(step, graph)
            else:
                result = {"note": "Unknown step type"}
            
            duration = int((time.perf_counter() - start_time) * 1000)
            graph.mark_step_completed(step_id, result, duration)
            
        except Exception as e:
            duration = int((time.perf_counter() - start_time) * 1000)
            graph.mark_step_failed(step_id, str(e), duration)
            log.error(f"Step {step_id} failed: {e}")
    
    async def _execute_tool(
        self,
        step: ExecutionStep,
        graph: ExecutionGraph,
    ) -> Any:
        """Execute a tool call step."""
        if not self.tool_registry:
            raise RuntimeError("Tool registry not configured")
        
        tool = self.tool_registry.get(step.tool_name)
        if not tool:
            raise ValueError(f"Tool not found: {step.tool_name}")
        
        if not tool.enabled:
            raise ValueError(f"Tool disabled: {step.tool_name}")
        
        # Get dependency results and merge into arguments if needed
        dep_results = graph.get_dependency_results(step.id)
        arguments = dict(step.arguments)
        
        # Allow arguments to reference dependency results via ${step_id}
        for key, value in arguments.items():
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                ref_step_id = value[2:-1]
                if ref_step_id in dep_results:
                    arguments[key] = dep_results[ref_step_id]
        
        # Execute tool with timeout
        result = await asyncio.wait_for(
            tool.handler(**arguments),
            timeout=tool.timeout_s,
        )
        
        return result
    
    def _aggregate_results(
        self,
        step: ExecutionStep,
        graph: ExecutionGraph,
    ) -> Any:
        """Aggregate results from dependency steps."""
        dep_results = graph.get_dependency_results(step.id)
        
        operation = step.metadata.get("operation", "aggregate")
        
        if operation == "aggregate":
            return {"aggregated": list(dep_results.values())}
        elif operation == "first_success":
            for result in dep_results.values():
                if isinstance(result, dict) and result.get("success"):
                    return result
            return {"success": False, "error": "No successful results"}
        else:
            return dep_results
    
    async def _evaluate_condition(
        self,
        step: ExecutionStep,
        graph: ExecutionGraph,
    ) -> Any:
        """Evaluate a conditional step."""
        dep_results = graph.get_dependency_results(step.id)
        condition = step.metadata.get("condition", "")
        
        # Simple condition evaluation (could be enhanced with LLM)
        # For now, just return the condition result
        return {
            "condition": condition,
            "dependency_results": dep_results,
            "evaluated": True,
        }


# === Helper Functions ===
def build_graph_from_plan(plan: List[Dict[str, Any]]) -> ExecutionGraph:
    """
    Build an ExecutionGraph from a plan generated by the autonomous agent.
    
    Args:
        plan: List of step dictionaries with format:
              {"tool": "tool_name", "args": {...}, "depends_on": [...]}
              
    Returns:
        ExecutionGraph ready for execution
    """
    graph = ExecutionGraph()
    
    for i, step_def in enumerate(plan):
        step_id = step_def.get("id", f"step_{i+1}")
        tool_name = step_def.get("tool")
        arguments = step_def.get("args", step_def.get("arguments", {}))
        dependencies = step_def.get("depends_on", step_def.get("dependencies", []))
        
        if tool_name:
            graph.add_tool_step(
                tool_name=tool_name,
                arguments=arguments,
                dependencies=dependencies,
                step_id=step_id,
            )
    
    return graph


def get_graph_executor(tool_registry: Optional[Any] = None) -> GraphExecutor:
    """
    Get a GraphExecutor instance.
    
    Args:
        tool_registry: Optional tool registry to use
        
    Returns:
        GraphExecutor instance
    """
    if tool_registry is None:
        try:
            from core.tool_registry import get_autonomous_tool_registry
            tool_registry = get_autonomous_tool_registry()
        except ImportError:
            pass
    
    return GraphExecutor(tool_registry=tool_registry)


# === Test ===
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("🧪 Testing Execution Graph")
        print("=" * 60)
        
        # Create a simple graph
        graph = ExecutionGraph()
        
        # Add parallel web searches
        step1 = graph.add_tool_step("web_search", {"query": "Bitcoin price"}, step_id="search_btc")
        step2 = graph.add_tool_step("web_search", {"query": "Ethereum price"}, step_id="search_eth")
        step3 = graph.add_tool_step("web_search", {"query": "Solana price"}, step_id="search_sol")
        
        # Add aggregation step
        step4 = graph.add_aggregation_step(
            dependencies=["search_btc", "search_eth", "search_sol"],
            step_id="aggregate_prices",
        )
        
        # Validate
        is_valid, error = graph.validate()
        print(f"Graph valid: {is_valid} (error: {error})")
        
        # Get parallel groups
        groups = graph.detect_parallelizable_groups()
        print(f"Parallel groups: {groups}")
        
        # Get execution order
        order = graph.get_execution_order()
        print(f"Execution order: {order}")
        
        # Serialize
        print(f"\nGraph structure:")
        import json
        print(json.dumps(graph.to_dict(), indent=2, default=str))
        
        print("\n✅ All tests passed!")
    
    asyncio.run(test())
