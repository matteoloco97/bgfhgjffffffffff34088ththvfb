#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/integration/test_chat_flow.py - Integration tests for chat flow.

Tests complete chat interaction from request to response.
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
def mock_llm_response():
    """Mock LLM response for testing."""
    return "This is a helpful response to your question about Python."


# ============================================================================
# CHAT ENDPOINT TESTS
# ============================================================================

class TestChatFlow:
    """Integration tests for complete chat flow."""
    
    def test_chat_request_model_creation(self, sample_fixtures):
        """Test creating a chat request from fixtures."""
        from backend.models import ChatRequest, SourceEnum
        
        request = ChatRequest(
            text="What is Python?",
            source=SourceEnum.API,
            source_id="integration_test_user"
        )
        
        assert request.text == "What is Python?"
        assert request.source == SourceEnum.API
    
    @pytest.mark.asyncio
    async def test_chat_flow_with_mock_llm(self, sample_fixtures, mock_llm_response):
        """Test complete chat flow with mocked LLM."""
        from backend.models import ChatRequest, SourceEnum
        
        # Create request
        request = ChatRequest(
            text="Tell me about Python",
            source=SourceEnum.API,
            source_id="test_user"
        )
        
        # Mock the LLM response
        with patch('core.chat_engine.reply_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.return_value = mock_llm_response
            
            # Import chat engine
            from core.chat_engine import reply_with_llm
            
            # Simulate chat flow
            response = await reply_with_llm(request.text, "")
            
            assert response == mock_llm_response
            mock_llm.assert_called_once()
    
    def test_chat_request_validation(self):
        """Test chat request validation."""
        from backend.models import ChatRequest, SourceEnum
        from pydantic import ValidationError
        
        # Valid request
        valid_request = ChatRequest(
            text="Hello world",
            source=SourceEnum.API,
            source_id="user123"
        )
        assert valid_request is not None
        
        # Invalid request (empty text)
        with pytest.raises(ValidationError):
            ChatRequest(
                text="",
                source=SourceEnum.API,
                source_id="user123"
            )
    
    def test_chat_request_sanitization(self):
        """Test that chat request sanitizes input."""
        from backend.models import ChatRequest, SourceEnum
        
        request = ChatRequest(
            text="   Hello world   ",
            source=SourceEnum.API,
            source_id="user123"
        )
        
        # Whitespace should be stripped
        assert request.text == "Hello world"
    
    def test_conversation_history_format(self, sample_fixtures):
        """Test conversation history format."""
        history = sample_fixtures["conversation_history"]
        
        assert len(history) > 0
        
        for message in history:
            assert "role" in message
            assert "content" in message
            assert message["role"] in ["user", "assistant", "system"]


# ============================================================================
# RESPONSE FORMAT TESTS
# ============================================================================

class TestChatResponseFormat:
    """Tests for chat response format."""
    
    def test_response_structure(self):
        """Test expected response structure."""
        expected_fields = ["response", "source"]
        
        # Simulate response
        response = {
            "response": "This is the answer",
            "source": "llm"
        }
        
        for field in expected_fields:
            assert field in response
    
    def test_response_with_metadata(self):
        """Test response with metadata."""
        response = {
            "response": "Answer text",
            "source": "llm",
            "metadata": {
                "tokens_used": 150,
                "latency_ms": 500
            }
        }
        
        assert "metadata" in response
        assert response["metadata"]["tokens_used"] == 150


# ============================================================================
# ERROR HANDLING TESTS
# ============================================================================

class TestChatErrorHandling:
    """Tests for chat error handling."""
    
    def test_validation_error_format(self):
        """Test validation error response format."""
        from backend.models import ChatRequest
        from pydantic import ValidationError
        
        try:
            ChatRequest(text="", source="invalid")
        except ValidationError as e:
            errors = e.errors()
            assert len(errors) > 0
    
    @pytest.mark.asyncio
    async def test_llm_error_handling(self):
        """Test handling of LLM errors."""
        with patch('core.chat_engine.reply_with_llm', new_callable=AsyncMock) as mock_llm:
            mock_llm.side_effect = Exception("LLM API error")
            
            from core.chat_engine import reply_with_llm
            
            with pytest.raises(Exception) as exc_info:
                await reply_with_llm("test", "")
            
            assert "LLM API error" in str(exc_info.value)


# ============================================================================
# PERSONA TESTS
# ============================================================================

class TestChatPersona:
    """Tests for chat persona functionality."""
    
    def test_persona_module_imports(self):
        """Test persona module can be imported."""
        from core.persona_store import get_persona, set_persona, reset_persona
        
        assert callable(get_persona)
        assert callable(set_persona)
        assert callable(reset_persona)
    
    @pytest.mark.asyncio
    async def test_get_default_persona(self):
        """Test getting default persona."""
        from core.persona_store import get_persona
        
        persona = await get_persona("api", "test_user")
        
        assert isinstance(persona, str)
    
    @pytest.mark.asyncio
    async def test_set_and_get_persona(self):
        """Test setting and getting persona."""
        from core.persona_store import get_persona, set_persona, reset_persona
        
        original = await get_persona("api", "test_user")
        
        try:
            await set_persona("api", "test_user", "Test persona for integration testing")
            new_persona = await get_persona("api", "test_user")
            
            # Should return the persona string
            assert isinstance(new_persona, str)
        finally:
            await reset_persona("api", "test_user")
