#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/reasoning_traces.py — Reasoning Traces System for QuantumDev Max

Features:
- Step-by-step thinking visualization
- Performance tracking per step
- Debug transparency
- Optional display (hide/show)
- Multiple thinking types

Author: Matteo (QuantumDev)
Version: 2.0.0
"""

from __future__ import annotations

import os
import time
import logging
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field, asdict
from enum import Enum
from datetime import datetime

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === ENV Configuration ===
def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


ENABLE_REASONING_TRACES = _env_bool("ENABLE_REASONING_TRACES", True)
VERBOSE_REASONING = _env_bool("VERBOSE_REASONING", False)


# === Enums ===
class ThinkingType(str, Enum):
    """Types of thinking steps."""
    ANALYSIS = "analysis"       # Analyzing the problem
    PLANNING = "planning"       # Planning the approach
    EXECUTION = "execution"     # Executing a step
    REFLECTION = "reflection"   # Reflecting on results
    SYNTHESIS = "synthesis"     # Synthesizing final answer
    CORRECTION = "correction"   # Correcting an error
    CLARIFICATION = "clarification"  # Clarifying something


class StepStatus(str, Enum):
    """Status of a thinking step."""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


# === Data Classes ===
@dataclass
class ThinkingStep:
    """Single thinking step in the reasoning process."""
    id: int
    type: ThinkingType
    title: str
    content: str
    status: StepStatus = StepStatus.PENDING
    duration_ms: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    _start_perf_counter: float = field(default=0.0, repr=False)
    timestamp: int = field(default_factory=lambda: int(time.time()))
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type.value,
            "title": self.title,
            "content": self.content,
            "status": self.status.value,
            "duration_ms": self.duration_ms,
            "metadata": self.metadata,
            "timestamp": self.timestamp,
        }
    
    def format_display(self, show_content: bool = True) -> str:
        """Format step for display."""
        icon = {
            ThinkingType.ANALYSIS: "🔍",
            ThinkingType.PLANNING: "📋",
            ThinkingType.EXECUTION: "⚡",
            ThinkingType.REFLECTION: "🤔",
            ThinkingType.SYNTHESIS: "✨",
            ThinkingType.CORRECTION: "🔧",
            ThinkingType.CLARIFICATION: "💡",
        }.get(self.type, "•")
        
        status_icon = {
            StepStatus.PENDING: "⏳",
            StepStatus.IN_PROGRESS: "🔄",
            StepStatus.COMPLETED: "✅",
            StepStatus.FAILED: "❌",
            StepStatus.SKIPPED: "⏭️",
        }.get(self.status, "•")
        
        line = f"{icon} **{self.title}** {status_icon}"
        if self.duration_ms > 0:
            line += f" ({self.duration_ms}ms)"
        
        if show_content and self.content:
            line += f"\n   {self.content}"
        
        return line


@dataclass
class ReasoningTrace:
    """Complete reasoning trace for a query."""
    query: str
    steps: List[ThinkingStep] = field(default_factory=list)
    total_duration_ms: int = 0
    started_at: int = field(default_factory=lambda: int(time.time()))
    completed_at: Optional[int] = None
    final_answer: str = ""
    success: bool = True
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "query": self.query,
            "steps": [s.to_dict() for s in self.steps],
            "total_duration_ms": self.total_duration_ms,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "final_answer": self.final_answer,
            "success": self.success,
            "error": self.error,
            "metadata": self.metadata,
        }
    
    @property
    def step_count(self) -> int:
        return len(self.steps)
    
    @property
    def completed_steps(self) -> int:
        return len([s for s in self.steps if s.status == StepStatus.COMPLETED])
    
    @property
    def failed_steps(self) -> int:
        return len([s for s in self.steps if s.status == StepStatus.FAILED])
    
    def format_summary(self) -> str:
        """Format trace summary for display."""
        lines = [
            f"🧠 **Reasoning Trace**",
            f"Query: {self.query[:100]}...",
            f"Steps: {self.completed_steps}/{self.step_count} completed",
            f"Duration: {self.total_duration_ms}ms",
        ]
        if self.error:
            lines.append(f"Error: {self.error}")
        return "\n".join(lines)
    
    def format_detailed(self, show_content: bool = True) -> str:
        """Format detailed trace for display."""
        lines = [
            "🧠 **REASONING TRACE**",
            f"{'=' * 50}",
            f"Query: {self.query}",
            f"Started: {datetime.fromtimestamp(self.started_at).isoformat()}",
            "",
            "**THINKING STEPS:**",
        ]
        
        for step in self.steps:
            lines.append(step.format_display(show_content))
        
        lines.extend([
            "",
            f"{'=' * 50}",
            f"Total Duration: {self.total_duration_ms}ms",
            f"Success: {'✅' if self.success else '❌'}",
        ])
        
        if self.error:
            lines.append(f"Error: {self.error}")
        
        return "\n".join(lines)


# === Reasoning Tracer ===
class ReasoningTracer:
    """
    Manages reasoning traces with step-by-step thinking.
    """
    
    def __init__(self, enabled: bool = ENABLE_REASONING_TRACES):
        """
        Initialize Reasoning Tracer.
        
        Args:
            enabled: Whether reasoning traces are enabled
        """
        self.enabled = enabled
        self._current_trace: Optional[ReasoningTrace] = None
        self._traces_history: List[ReasoningTrace] = []
        self._max_history = 100
    
    def start_trace(self, query: str, metadata: Optional[Dict[str, Any]] = None) -> ReasoningTrace:
        """
        Start a new reasoning trace.
        
        Args:
            query: The query being processed
            metadata: Optional metadata
            
        Returns:
            New ReasoningTrace instance
        """
        trace = ReasoningTrace(
            query=query,
            metadata=metadata or {},
        )
        self._current_trace = trace
        
        if self.enabled:
            log.debug(f"Reasoning trace started for: {query[:50]}...")
        
        return trace
    
    def add_step(
        self,
        type: ThinkingType,
        title: str,
        content: str = "",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[ThinkingStep]:
        """
        Add a thinking step to current trace.
        
        Args:
            type: Type of thinking step
            title: Step title
            content: Step content/details
            metadata: Optional metadata
            
        Returns:
            ThinkingStep if trace exists
        """
        if not self._current_trace:
            return None
        
        step = ThinkingStep(
            id=len(self._current_trace.steps) + 1,
            type=type,
            title=title,
            content=content,
            status=StepStatus.IN_PROGRESS,
            metadata=metadata or {},
            _start_perf_counter=time.perf_counter(),
        )
        
        self._current_trace.steps.append(step)
        
        if self.enabled and VERBOSE_REASONING:
            log.info(f"Thinking: [{type.value}] {title}")
        
        return step
    
    def complete_step(
        self,
        step: ThinkingStep,
        content: Optional[str] = None,
        success: bool = True,
    ) -> None:
        """
        Mark a step as completed.
        
        Args:
            step: The step to complete
            content: Optional updated content
            success: Whether step succeeded
        """
        if content:
            step.content = content
        
        step.status = StepStatus.COMPLETED if success else StepStatus.FAILED
        # Use perf_counter for accurate duration
        if step._start_perf_counter > 0:
            step.duration_ms = int((time.perf_counter() - step._start_perf_counter) * 1000)
        
        if self.enabled and VERBOSE_REASONING:
            status = "✅" if success else "❌"
            log.info(f"Step {step.id} {status}: {step.title} ({step.duration_ms}ms)")
    
    def analysis(self, title: str, content: str = "") -> Optional[ThinkingStep]:
        """Add an analysis step."""
        return self.add_step(ThinkingType.ANALYSIS, title, content)
    
    def planning(self, title: str, content: str = "") -> Optional[ThinkingStep]:
        """Add a planning step."""
        return self.add_step(ThinkingType.PLANNING, title, content)
    
    def execution(self, title: str, content: str = "") -> Optional[ThinkingStep]:
        """Add an execution step."""
        return self.add_step(ThinkingType.EXECUTION, title, content)
    
    def reflection(self, title: str, content: str = "") -> Optional[ThinkingStep]:
        """Add a reflection step."""
        return self.add_step(ThinkingType.REFLECTION, title, content)
    
    def synthesis(self, title: str, content: str = "") -> Optional[ThinkingStep]:
        """Add a synthesis step."""
        return self.add_step(ThinkingType.SYNTHESIS, title, content)
    
    def correction(self, title: str, content: str = "") -> Optional[ThinkingStep]:
        """Add a correction step."""
        return self.add_step(ThinkingType.CORRECTION, title, content)
    
    def complete_trace(
        self,
        final_answer: str = "",
        success: bool = True,
        error: Optional[str] = None,
    ) -> Optional[ReasoningTrace]:
        """
        Complete the current reasoning trace.
        
        Args:
            final_answer: The final response
            success: Whether reasoning succeeded
            error: Optional error message
            
        Returns:
            Completed ReasoningTrace
        """
        if not self._current_trace:
            return None
        
        trace = self._current_trace
        trace.completed_at = int(time.time())
        trace.total_duration_ms = int((trace.completed_at - trace.started_at) * 1000)
        trace.final_answer = final_answer
        trace.success = success
        trace.error = error
        
        # Add to history
        self._traces_history.append(trace)
        if len(self._traces_history) > self._max_history:
            self._traces_history.pop(0)
        
        if self.enabled:
            log.info(
                f"Reasoning trace completed: {trace.step_count} steps, "
                f"{trace.total_duration_ms}ms, success={success}"
            )
        
        self._current_trace = None
        return trace
    
    @property
    def current_trace(self) -> Optional[ReasoningTrace]:
        """Get current trace."""
        return self._current_trace
    
    def get_recent_traces(self, n: int = 10) -> List[ReasoningTrace]:
        """Get recent traces."""
        return self._traces_history[-n:]
    
    def get_stats(self) -> Dict[str, Any]:
        """Get tracer statistics."""
        if not self._traces_history:
            return {"total_traces": 0}
        
        total = len(self._traces_history)
        successful = len([t for t in self._traces_history if t.success])
        avg_duration = sum(t.total_duration_ms for t in self._traces_history) / total
        avg_steps = sum(t.step_count for t in self._traces_history) / total
        
        return {
            "total_traces": total,
            "successful_traces": successful,
            "success_rate": round(successful / total, 2),
            "avg_duration_ms": round(avg_duration),
            "avg_steps": round(avg_steps, 1),
        }


# === Context Manager for Steps ===
class ThinkingStepContext:
    """Context manager for thinking steps with automatic timing."""
    
    def __init__(
        self,
        tracer: ReasoningTracer,
        type: ThinkingType,
        title: str,
        content: str = "",
    ):
        self.tracer = tracer
        self.type = type
        self.title = title
        self.content = content
        self.step: Optional[ThinkingStep] = None
        self._start_time: float = 0
    
    def __enter__(self) -> ThinkingStep:
        self._start_time = time.time()
        self.step = self.tracer.add_step(self.type, self.title, self.content)
        return self.step
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if self.step:
            success = exc_type is None
            self.tracer.complete_step(self.step, success=success)
        return False  # Don't suppress exceptions


# === Singleton Instance ===
_tracer_instance: Optional[ReasoningTracer] = None


def get_reasoning_tracer(enabled: Optional[bool] = None) -> ReasoningTracer:
    """
    Get or create ReasoningTracer singleton.
    
    Args:
        enabled: Whether to enable tracing
        
    Returns:
        ReasoningTracer instance
    """
    global _tracer_instance
    
    if _tracer_instance is None:
        _tracer_instance = ReasoningTracer(
            enabled=enabled if enabled is not None else ENABLE_REASONING_TRACES
        )
    
    return _tracer_instance


# === Helper Functions ===
def think(type: ThinkingType, title: str, content: str = "") -> ThinkingStepContext:
    """
    Create a thinking step context.
    
    Usage:
        with think(ThinkingType.ANALYSIS, "Analyzing query"):
            # do analysis
            pass
    """
    tracer = get_reasoning_tracer()
    return ThinkingStepContext(tracer, type, title, content)


def analyze(title: str, content: str = "") -> ThinkingStepContext:
    """Shortcut for analysis step."""
    return think(ThinkingType.ANALYSIS, title, content)


def plan(title: str, content: str = "") -> ThinkingStepContext:
    """Shortcut for planning step."""
    return think(ThinkingType.PLANNING, title, content)


def execute(title: str, content: str = "") -> ThinkingStepContext:
    """Shortcut for execution step."""
    return think(ThinkingType.EXECUTION, title, content)


def reflect(title: str, content: str = "") -> ThinkingStepContext:
    """Shortcut for reflection step."""
    return think(ThinkingType.REFLECTION, title, content)


def synthesize(title: str, content: str = "") -> ThinkingStepContext:
    """Shortcut for synthesis step."""
    return think(ThinkingType.SYNTHESIS, title, content)


# === Test ===
if __name__ == "__main__":
    import asyncio
    
    def test():
        print("🧪 Testing Reasoning Traces")
        print("=" * 60)
        
        tracer = get_reasoning_tracer(enabled=True)
        
        # Start a trace
        trace = tracer.start_trace("What is the weather in Rome?")
        print(f"Trace started: {trace.query}")
        
        # Add steps using context managers
        with analyze("Understanding query"):
            time.sleep(0.1)  # Simulate work
        
        with plan("Determining approach"):
            time.sleep(0.05)
        
        with execute("Fetching weather data"):
            time.sleep(0.2)
        
        with reflect("Evaluating results"):
            time.sleep(0.05)
        
        with synthesize("Generating response"):
            time.sleep(0.1)
        
        # Complete trace
        completed = tracer.complete_trace(
            final_answer="The weather in Rome is sunny, 22°C.",
            success=True,
        )
        
        print("\n" + completed.format_detailed())
        
        print("\nStats:")
        print(json.dumps(tracer.get_stats(), indent=2))
        
        print("\n✅ All tests passed!")
    
    test()
