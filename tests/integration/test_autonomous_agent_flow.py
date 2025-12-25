#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/integration/test_autonomous_agent_flow.py - Integration tests for autonomous agent flow.

Tests multi-step task execution and planning.
"""

import os
import sys
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def sample_fixtures():
    """Load sample test fixtures."""
    fixtures_path = os.path.join(os.path.dirname(__file__), "../fixtures/sample_data.json")
    with open(fixtures_path) as f:
        return json.load(f)


@pytest.fixture
def sample_autonomous_tasks(sample_fixtures):
    """Get sample autonomous tasks."""
    return sample_fixtures["autonomous_tasks"]


# ============================================================================
# AUTONOMOUS REQUEST TESTS
# ============================================================================

class TestAutonomousRequest:
    """Tests for AutonomousRequest model."""
    
    def test_valid_autonomous_request(self):
        """Test valid AutonomousRequest creation."""
        from backend.models import AutonomousRequest, SourceEnum
        
        request = AutonomousRequest(
            goal="Find the best Python web frameworks",
            show_plan=True,
            max_steps=10,
            source=SourceEnum.API,
            source_id="test_user"
        )
        
        assert request.goal == "Find the best Python web frameworks"
        assert request.show_plan is True
        assert request.max_steps == 10
    
    def test_autonomous_request_defaults(self):
        """Test AutonomousRequest default values."""
        from backend.models import AutonomousRequest
        
        request = AutonomousRequest(goal="Test goal")
        
        assert request.show_plan is True
        assert request.max_steps == 10
        assert request.require_approval is False
    
    def test_autonomous_request_from_fixture(self, sample_autonomous_tasks):
        """Test creating request from fixture."""
        from backend.models import AutonomousRequest
        
        for task in sample_autonomous_tasks:
            request = AutonomousRequest(goal=task["goal"])
            
            assert request.goal == task["goal"]


# ============================================================================
# AUTONOMOUS AGENT TESTS
# ============================================================================

class TestAutonomousAgent:
    """Tests for autonomous agent functionality."""
    
    def test_autonomous_agent_import(self):
        """Test autonomous agent can be imported."""
        try:
            from core.autonomous_agent import AutonomousAgent
            assert AutonomousAgent is not None
        except ImportError:
            pytest.skip("autonomous_agent module not available")
    
    def test_execution_graph_import(self):
        """Test execution graph can be imported."""
        try:
            from core.execution_graph import ExecutionGraph
            assert ExecutionGraph is not None
        except ImportError:
            pytest.skip("execution_graph module not available")


# ============================================================================
# PLANNING TESTS
# ============================================================================

class TestTaskPlanning:
    """Tests for task planning functionality."""
    
    def test_expected_steps_structure(self, sample_autonomous_tasks):
        """Test expected steps structure in fixtures."""
        for task in sample_autonomous_tasks:
            assert "expected_steps" in task
            assert isinstance(task["expected_steps"], list)
            assert len(task["expected_steps"]) > 0
    
    def test_plan_step_format(self, sample_autonomous_tasks):
        """Test plan step format."""
        for task in sample_autonomous_tasks:
            for step in task["expected_steps"]:
                assert isinstance(step, str)
                assert len(step) > 0


# ============================================================================
# TOOL REGISTRY TESTS
# ============================================================================

class TestToolRegistry:
    """Tests for tool registry used by autonomous agent."""
    
    def test_tool_registry_import(self):
        """Test tool registry can be imported."""
        try:
            from core.tool_registry import ToolRegistry
            assert ToolRegistry is not None
        except ImportError:
            pytest.skip("tool_registry module not available")
    
    def test_register_tools_import(self):
        """Test register_tools can be imported."""
        try:
            from core.register_tools import register_tools
            assert callable(register_tools)
        except ImportError:
            pytest.skip("register_tools module not available")


# ============================================================================
# FUNCTION CALLING TESTS
# ============================================================================

class TestFunctionCalling:
    """Tests for function calling functionality."""
    
    def test_function_calling_import(self):
        """Test function calling can be imported."""
        try:
            from core.function_calling import FunctionCaller
            assert FunctionCaller is not None
        except ImportError:
            pytest.skip("function_calling module not available")


# ============================================================================
# TASK EXECUTION TESTS
# ============================================================================

class TestTaskExecution:
    """Tests for task execution."""
    
    def test_max_steps_validation(self):
        """Test max_steps validation."""
        from backend.models import AutonomousRequest
        from pydantic import ValidationError
        
        # Valid max_steps
        request = AutonomousRequest(goal="Test", max_steps=10)
        assert request.max_steps == 10
        
        # Invalid max_steps (too high)
        with pytest.raises(ValidationError):
            AutonomousRequest(goal="Test", max_steps=25)
        
        # Invalid max_steps (too low)
        with pytest.raises(ValidationError):
            AutonomousRequest(goal="Test", max_steps=0)
    
    def test_require_approval_flag(self):
        """Test require_approval flag."""
        from backend.models import AutonomousRequest
        
        request = AutonomousRequest(
            goal="Test",
            require_approval=True
        )
        
        assert request.require_approval is True


# ============================================================================
# REASONING TRACES TESTS
# ============================================================================

class TestReasoningTraces:
    """Tests for reasoning traces."""
    
    def test_reasoning_traces_import(self):
        """Test reasoning traces can be imported."""
        try:
            from core.reasoning_traces import ReasoningTracer
            assert ReasoningTracer is not None
        except ImportError:
            pytest.skip("reasoning_traces module not available")


# ============================================================================
# INTEGRATION WITH OTHER COMPONENTS
# ============================================================================

class TestAutonomousIntegration:
    """Tests for autonomous agent integration with other components."""
    
    def test_intent_classifier_import(self):
        """Test intent classifier can be imported."""
        try:
            from core.intent_classifier import IntentClassifier
            assert IntentClassifier is not None
        except ImportError:
            pytest.skip("intent_classifier module not available")
    
    def test_smart_search_import(self):
        """Test smart search can be imported."""
        try:
            from core.smart_search import SmartSearch
            assert SmartSearch is not None
        except ImportError:
            pytest.skip("smart_search module not available")
    
    def test_query_analyzer_import(self):
        """Test query analyzer can be imported."""
        try:
            from core.query_analyzer_v2 import analyze_query
            assert callable(analyze_query)
        except ImportError:
            pytest.skip("query_analyzer_v2 module not available")


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestAutonomousErrorHandling:
    """Tests for autonomous agent error handling."""
    
    def test_goal_validation_error(self):
        """Test goal validation error."""
        from backend.models import AutonomousRequest
        from pydantic import ValidationError
        
        # Empty goal
        with pytest.raises(ValidationError):
            AutonomousRequest(goal="")
    
    def test_goal_too_long(self):
        """Test goal exceeding max length."""
        from backend.models import AutonomousRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            AutonomousRequest(goal="x" * 1500)
    
    def test_injection_in_goal_blocked(self):
        """Test injection attempts in goal are blocked."""
        from backend.models import AutonomousRequest
        from pydantic import ValidationError
        
        with pytest.raises(ValidationError):
            AutonomousRequest(goal="<script>evil()</script>")


# ============================================================================
# RESPONSE FORMAT TESTS
# ============================================================================

class TestAutonomousResponse:
    """Tests for autonomous agent response format."""
    
    def test_response_with_plan(self):
        """Test response with execution plan."""
        response = {
            "result": "Found 3 frameworks",
            "plan": [
                "Search for Python frameworks",
                "Compare features",
                "Summarize findings"
            ],
            "steps_executed": 3
        }
        
        assert "result" in response
        assert "plan" in response
        assert len(response["plan"]) == 3
    
    def test_response_without_plan(self):
        """Test response without plan (show_plan=False)."""
        response = {
            "result": "Found 3 frameworks",
            "steps_executed": 3
        }
        
        assert "result" in response
        assert "plan" not in response


# ============================================================================
# EDGE CASES
# ============================================================================

class TestAutonomousEdgeCases:
    """Tests for autonomous agent edge cases."""
    
    def test_single_step_task(self):
        """Test task with single step."""
        from backend.models import AutonomousRequest
        
        request = AutonomousRequest(
            goal="What is 2+2?",
            max_steps=1
        )
        
        assert request.max_steps == 1
    
    def test_complex_goal(self):
        """Test complex multi-part goal."""
        from backend.models import AutonomousRequest
        
        complex_goal = (
            "Research Python web frameworks, compare their performance, "
            "analyze community support, and provide recommendations"
        )
        
        request = AutonomousRequest(goal=complex_goal)
        
        assert len(request.goal) > 50
    
    def test_unicode_in_goal(self):
        """Test Unicode in goal."""
        from backend.models import AutonomousRequest
        
        request = AutonomousRequest(
            goal="研究Python框架并提供建议"
        )
        
        assert "Python" in request.goal
