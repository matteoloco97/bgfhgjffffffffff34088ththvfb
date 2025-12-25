#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/unit/test_input_validation.py - Unit tests for Pydantic input validation.

Tests for all request models including ChatRequest, WebSearchRequest,
WebSummarizeRequest, AutonomousRequest, and ToolRequest.
"""

import os
import sys
import pytest
from pydantic import ValidationError

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "../.."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from backend.models import (
    ChatRequest,
    WebSearchRequest,
    WebSummarizeRequest,
    AutonomousRequest,
    ToolRequest,
    SourceEnum,
    ToolNameEnum,
    sanitize_html,
    normalize_unicode,
    check_injection_patterns,
    check_nested_depth,
)


# ============================================================================
# UTILITY FUNCTION TESTS
# ============================================================================

class TestSanitizeHtml:
    """Tests for HTML sanitization utility."""
    
    def test_sanitize_empty_string(self):
        """Test sanitization of empty string."""
        result = sanitize_html("")
        assert result == ""
    
    def test_sanitize_none(self):
        """Test sanitization of None."""
        result = sanitize_html(None)
        assert result is None
    
    def test_sanitize_removes_script_tags(self):
        """Test that script tags are removed."""
        html = "<script>alert('xss')</script>Hello"
        result = sanitize_html(html)
        assert "<script>" not in result
        assert "alert" not in result.lower() or "Hello" in result
    
    def test_sanitize_removes_malformed_tags(self):
        """Test that malformed tags are removed."""
        html = "<script src=evil.js Hello"
        result = sanitize_html(html)
        # Malformed tag content should be removed
        assert "<script" not in result.lower()
    
    def test_sanitize_preserves_legitimate_content(self):
        """Test that legitimate content is preserved."""
        text = "Hello world, 2 > 1 and 3 < 4"
        result = sanitize_html(text)
        assert "Hello world" in result
    
    def test_sanitize_escapes_special_chars(self):
        """Test that special characters are escaped."""
        text = "<>&"
        result = sanitize_html(text)
        assert "&lt;" in result or "&gt;" in result or "&amp;" in result


class TestNormalizeUnicode:
    """Tests for Unicode normalization utility."""
    
    def test_normalize_empty_string(self):
        """Test normalization of empty string."""
        result = normalize_unicode("")
        assert result == ""
    
    def test_normalize_none(self):
        """Test normalization of None."""
        result = normalize_unicode(None)
        assert result is None
    
    def test_normalize_nfc_form(self):
        """Test normalization to NFC form."""
        # é can be represented as single char (NFC) or e + combining accent (NFD)
        nfd_form = "cafe\u0301"  # e + combining acute accent
        result = normalize_unicode(nfd_form)
        assert len(result) == len("café")  # NFC is more compact
    
    def test_normalize_ascii_unchanged(self):
        """Test that ASCII is unchanged."""
        text = "Hello World"
        result = normalize_unicode(text)
        assert result == text


class TestCheckInjectionPatterns:
    """Tests for injection pattern detection."""
    
    def test_safe_text_passes(self):
        """Test that safe text passes validation."""
        safe_texts = [
            "Hello World",
            "What's the weather?",
            "How do I use Python?",
            "2 + 2 = 4",
        ]
        
        for text in safe_texts:
            result = check_injection_patterns(text, "test")
            assert result == text
    
    def test_sql_injection_blocked(self):
        """Test that SQL injection is blocked."""
        sql_attempts = [
            "'; DROP TABLE users; --",
            "UNION SELECT * FROM passwords",
            "INSERT INTO users VALUES('hacker')",
        ]
        
        for text in sql_attempts:
            with pytest.raises(ValueError) as exc_info:
                check_injection_patterns(text, "test")
            assert "dangerous" in str(exc_info.value).lower()
    
    def test_xss_injection_blocked(self):
        """Test that XSS injection is blocked."""
        xss_attempts = [
            "<script>alert('xss')</script>",
            "javascript:void(0)",
            "<iframe src='evil.com'>",
            "onclick=malicious()",
        ]
        
        for text in xss_attempts:
            with pytest.raises(ValueError) as exc_info:
                check_injection_patterns(text, "test")
            assert "dangerous" in str(exc_info.value).lower()
    
    def test_path_traversal_blocked(self):
        """Test that path traversal is blocked."""
        path_attempts = [
            "../../../etc/passwd",
            "..\\..\\windows\\system32",
            "~/secret_file",
        ]
        
        for text in path_attempts:
            with pytest.raises(ValueError) as exc_info:
                check_injection_patterns(text, "test")
            assert "traversal" in str(exc_info.value).lower()


class TestCheckNestedDepth:
    """Tests for nested object depth checking."""
    
    def test_shallow_object_passes(self):
        """Test that shallow object passes."""
        obj = {"a": {"b": "value"}}
        check_nested_depth(obj, max_depth=5)
        # Should not raise
    
    def test_deep_object_fails(self):
        """Test that deeply nested object fails."""
        deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "too deep"}}}}}}}
        
        with pytest.raises(ValueError) as exc_info:
            check_nested_depth(deep, max_depth=5)
        assert "depth" in str(exc_info.value).lower()
    
    def test_flat_object_passes(self):
        """Test that flat object passes."""
        obj = {"a": 1, "b": 2, "c": 3}
        check_nested_depth(obj, max_depth=5)
        # Should not raise
    
    def test_list_nesting(self):
        """Test nesting in lists."""
        obj = [[[[[["too deep"]]]]]]
        
        with pytest.raises(ValueError) as exc_info:
            check_nested_depth(obj, max_depth=5)
        assert "depth" in str(exc_info.value).lower()


# ============================================================================
# CHAT REQUEST TESTS
# ============================================================================

class TestChatRequest:
    """Tests for ChatRequest model."""
    
    def test_valid_chat_request(self):
        """Test valid ChatRequest creation."""
        req = ChatRequest(
            text="What's the weather today?",
            source=SourceEnum.API,
            source_id="user123"
        )
        
        assert req.text == "What's the weather today?"
        assert req.source == SourceEnum.API
        assert req.source_id == "user123"
    
    def test_chat_request_defaults(self):
        """Test ChatRequest default values."""
        req = ChatRequest(text="Hello")
        
        assert req.source == SourceEnum.API
        assert req.source_id == "default"
    
    def test_chat_request_empty_text_fails(self):
        """Test that empty text fails validation."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(text="", source=SourceEnum.API, source_id="user123")
        assert "text" in str(exc_info.value)
    
    def test_chat_request_whitespace_only_fails(self):
        """Test that whitespace-only text fails."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(text="   ", source=SourceEnum.API, source_id="user123")
        assert "text" in str(exc_info.value).lower()
    
    def test_chat_request_text_too_long(self):
        """Test that text exceeding max length fails."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(text="a" * 6000, source=SourceEnum.API, source_id="user123")
        assert "text" in str(exc_info.value)
    
    def test_chat_request_xss_blocked(self):
        """Test that XSS attempts are blocked."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(
                text="<script>alert('xss')</script>",
                source=SourceEnum.API,
                source_id="user123"
            )
        assert "dangerous" in str(exc_info.value).lower()
    
    def test_chat_request_sql_injection_blocked(self):
        """Test that SQL injection is blocked."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(
                text="'; DROP TABLE users; --",
                source=SourceEnum.API,
                source_id="user123"
            )
        assert "dangerous" in str(exc_info.value).lower()
    
    def test_chat_request_whitespace_stripped(self):
        """Test that whitespace is stripped from text."""
        req = ChatRequest(
            text="  Hello world  ",
            source=SourceEnum.API,
            source_id="user123"
        )
        assert req.text == "Hello world"
    
    def test_chat_request_invalid_source_id(self):
        """Test that invalid source_id characters fail."""
        with pytest.raises(ValidationError) as exc_info:
            ChatRequest(
                text="Hello",
                source=SourceEnum.API,
                source_id="user@email.com"
            )
        assert "source_id" in str(exc_info.value)
    
    def test_chat_request_valid_source_id_chars(self):
        """Test valid source_id characters."""
        valid_ids = ["user123", "user_123", "user-123", "user:123"]
        
        for source_id in valid_ids:
            req = ChatRequest(text="Hello", source_id=source_id)
            assert req.source_id == source_id
    
    def test_chat_request_unicode_text(self):
        """Test Unicode text is accepted."""
        req = ChatRequest(
            text="こんにちは世界",
            source=SourceEnum.API,
            source_id="user123"
        )
        assert "こんにちは" in req.text


# ============================================================================
# WEB SEARCH REQUEST TESTS
# ============================================================================

class TestWebSearchRequest:
    """Tests for WebSearchRequest model."""
    
    def test_valid_web_search_request(self):
        """Test valid WebSearchRequest creation."""
        req = WebSearchRequest(q="Python tutorial", k=10, summarize_top=3)
        
        assert req.q == "Python tutorial"
        assert req.k == 10
        assert req.summarize_top == 3
    
    def test_web_search_request_defaults(self):
        """Test WebSearchRequest default values."""
        req = WebSearchRequest(q="test")
        
        assert req.k == 6
        assert req.summarize_top == 2
    
    def test_web_search_query_too_long(self):
        """Test that query exceeding max length fails."""
        with pytest.raises(ValidationError) as exc_info:
            WebSearchRequest(q="a" * 600)
        assert "q" in str(exc_info.value)
    
    def test_web_search_k_out_of_range_high(self):
        """Test that k exceeding max fails."""
        with pytest.raises(ValidationError) as exc_info:
            WebSearchRequest(q="test", k=25)
        assert "k" in str(exc_info.value)
    
    def test_web_search_k_out_of_range_low(self):
        """Test that k below min fails."""
        with pytest.raises(ValidationError) as exc_info:
            WebSearchRequest(q="test", k=0)
        assert "k" in str(exc_info.value)
    
    def test_web_search_injection_blocked(self):
        """Test that injection is blocked in query."""
        with pytest.raises(ValidationError) as exc_info:
            WebSearchRequest(q="<iframe src='evil.com'></iframe>")
        assert "dangerous" in str(exc_info.value).lower()


# ============================================================================
# WEB SUMMARIZE REQUEST TESTS
# ============================================================================

class TestWebSummarizeRequest:
    """Tests for WebSummarizeRequest model."""
    
    def test_valid_request_with_url(self):
        """Test valid request with URL."""
        req = WebSummarizeRequest(url="https://example.com/article")
        
        assert req.url == "https://example.com/article"
        assert req.q is None
    
    def test_valid_request_with_query(self):
        """Test valid request with query."""
        req = WebSummarizeRequest(q="Python asyncio")
        
        assert req.q == "Python asyncio"
        assert req.url is None
    
    def test_both_url_and_query_fails(self):
        """Test that providing both url and query fails."""
        with pytest.raises(ValidationError) as exc_info:
            WebSummarizeRequest(url="https://example.com", q="test")
        assert "either" in str(exc_info.value).lower()
    
    def test_neither_url_nor_query_fails(self):
        """Test that providing neither url nor query fails."""
        with pytest.raises(ValidationError) as exc_info:
            WebSummarizeRequest(return_sources=True)
        assert "either" in str(exc_info.value).lower()
    
    def test_javascript_protocol_blocked(self):
        """Test that javascript: protocol is blocked."""
        with pytest.raises(ValidationError) as exc_info:
            WebSummarizeRequest(url="javascript:alert('xss')")
        error_msg = str(exc_info.value).lower()
        assert "url must start with http" in error_msg or "protocol" in error_msg
    
    def test_path_traversal_blocked(self):
        """Test that path traversal in URL is blocked."""
        with pytest.raises(ValidationError) as exc_info:
            WebSummarizeRequest(url="https://example.com/../../../etc/passwd")
        assert "traversal" in str(exc_info.value).lower()
    
    def test_valid_https_url(self):
        """Test valid HTTPS URL."""
        req = WebSummarizeRequest(url="https://secure.example.com/page")
        assert req.url == "https://secure.example.com/page"
    
    def test_valid_http_url(self):
        """Test valid HTTP URL."""
        req = WebSummarizeRequest(url="http://example.com/page")
        assert req.url == "http://example.com/page"


# ============================================================================
# AUTONOMOUS REQUEST TESTS
# ============================================================================

class TestAutonomousRequest:
    """Tests for AutonomousRequest model."""
    
    def test_valid_autonomous_request(self):
        """Test valid AutonomousRequest creation."""
        req = AutonomousRequest(
            goal="Find the best Python frameworks",
            show_plan=True,
            max_steps=10
        )
        
        assert req.goal == "Find the best Python frameworks"
        assert req.show_plan is True
        assert req.max_steps == 10
    
    def test_autonomous_request_defaults(self):
        """Test AutonomousRequest default values."""
        req = AutonomousRequest(goal="Test goal")
        
        assert req.show_plan is True
        assert req.max_steps == 10
        assert req.require_approval is False
    
    def test_goal_too_long(self):
        """Test that goal exceeding max length fails."""
        with pytest.raises(ValidationError) as exc_info:
            AutonomousRequest(goal="a" * 1500)
        assert "goal" in str(exc_info.value)
    
    def test_max_steps_out_of_range_high(self):
        """Test that max_steps exceeding max fails."""
        with pytest.raises(ValidationError) as exc_info:
            AutonomousRequest(goal="Test", max_steps=25)
        assert "max_steps" in str(exc_info.value)
    
    def test_max_steps_out_of_range_low(self):
        """Test that max_steps below min fails."""
        with pytest.raises(ValidationError) as exc_info:
            AutonomousRequest(goal="Test", max_steps=0)
        assert "max_steps" in str(exc_info.value)
    
    def test_injection_blocked_in_goal(self):
        """Test that injection is blocked in goal."""
        with pytest.raises(ValidationError) as exc_info:
            AutonomousRequest(goal="<script>malicious()</script>")
        assert "dangerous" in str(exc_info.value).lower()


# ============================================================================
# TOOL REQUEST TESTS
# ============================================================================

class TestToolRequest:
    """Tests for ToolRequest model."""
    
    def test_valid_tool_request(self):
        """Test valid ToolRequest creation."""
        req = ToolRequest(
            tool_name=ToolNameEnum.MATH,
            parameters={"expr": "2 + 2"}
        )
        
        assert req.tool_name == ToolNameEnum.MATH
        assert req.parameters == {"expr": "2 + 2"}
    
    def test_tool_request_defaults(self):
        """Test ToolRequest default values."""
        req = ToolRequest(tool_name=ToolNameEnum.MATH)
        
        assert req.parameters == {}
        assert req.source == SourceEnum.API
    
    def test_nested_depth_limit(self):
        """Test that nesting depth limit is enforced."""
        deep = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "deep"}}}}}}}
        
        with pytest.raises(ValidationError) as exc_info:
            ToolRequest(tool_name=ToolNameEnum.MATH, parameters=deep)
        assert "depth" in str(exc_info.value).lower()
    
    def test_parameters_not_dict_fails(self):
        """Test that non-dict parameters fail."""
        with pytest.raises(ValidationError) as exc_info:
            ToolRequest(tool_name=ToolNameEnum.MATH, parameters="not a dict")
        assert "parameters" in str(exc_info.value)
    
    def test_valid_math_expression(self):
        """Test that math expressions are allowed."""
        req = ToolRequest(
            tool_name=ToolNameEnum.MATH,
            parameters={"expr": "2 + 2 * 3 - 1"}
        )
        assert req.parameters["expr"] == "2 + 2 * 3 - 1"


# ============================================================================
# SOURCE ENUM TESTS
# ============================================================================

class TestSourceEnum:
    """Tests for SourceEnum."""
    
    def test_all_source_values(self):
        """Test all source enum values exist."""
        expected_sources = ["api", "tg", "gui", "web", "system", "test"]
        
        for source in expected_sources:
            assert hasattr(SourceEnum, source.upper())
    
    def test_source_enum_values(self):
        """Test source enum value strings."""
        assert SourceEnum.API.value == "api"
        assert SourceEnum.TG.value == "tg"


# ============================================================================
# TOOL NAME ENUM TESTS
# ============================================================================

class TestToolNameEnum:
    """Tests for ToolNameEnum."""
    
    def test_all_tool_names(self):
        """Test all tool name enum values exist."""
        expected_tools = ["math", "python", "web_search", "web_summarize", "code_exec", "file_upload", "file_query", "ocr"]
        
        for tool in expected_tools:
            assert hasattr(ToolNameEnum, tool.upper())
    
    def test_tool_enum_values(self):
        """Test tool enum value strings."""
        assert ToolNameEnum.MATH.value == "math"
        assert ToolNameEnum.WEB_SEARCH.value == "web_search"


# ============================================================================
# EDGE CASES
# ============================================================================

class TestInputValidationEdgeCases:
    """Tests for input validation edge cases."""
    
    def test_emoji_in_text(self):
        """Test that emoji are accepted in text."""
        req = ChatRequest(text="Hello 🚀 World 🎉")
        assert "🚀" in req.text
        assert "🎉" in req.text
    
    def test_unicode_normalization_in_request(self):
        """Test Unicode normalization in request."""
        req = ChatRequest(text="café")
        assert req.text == "café"
    
    def test_very_short_valid_text(self):
        """Test very short but valid text."""
        req = ChatRequest(text="a")
        assert req.text == "a"
    
    def test_max_length_text(self):
        """Test text at exactly max length."""
        text = "a" * 5000
        req = ChatRequest(text=text)
        assert len(req.text) == 5000
    
    def test_mixed_case_source_id(self):
        """Test mixed case source_id."""
        req = ChatRequest(text="Hello", source_id="User_123_Test")
        assert req.source_id == "User_123_Test"
    
    def test_system_prompt_validation(self):
        """Test system_prompt validation."""
        req = ChatRequest(
            text="Hello",
            system_prompt="You are a helpful assistant"
        )
        assert req.system_prompt == "You are a helpful assistant"
    
    def test_system_prompt_injection_blocked(self):
        """Test that injection in system_prompt is blocked."""
        with pytest.raises(ValidationError):
            ChatRequest(
                text="Hello",
                system_prompt="<script>evil()</script>"
            )
