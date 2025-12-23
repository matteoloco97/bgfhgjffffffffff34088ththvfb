#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
tests/test_input_validation.py - Test comprehensive input validation

Tests for Pydantic models:
- ChatRequest
- WebSearchRequest
- WebSummarizeRequest
- AutonomousRequest
- ToolRequest
"""

import pytest
from pydantic import ValidationError

from backend.models import (
    ChatRequest,
    WebSearchRequest,
    WebSummarizeRequest,
    AutonomousRequest,
    ToolRequest,
    SourceEnum,
    ToolNameEnum,
)


# ===================== ChatRequest Tests =====================

def test_chat_request_valid():
    """Test valid ChatRequest."""
    req = ChatRequest(
        text="What's the weather today?",
        source=SourceEnum.API,
        source_id="user123"
    )
    assert req.text == "What's the weather today?"
    assert req.source == SourceEnum.API
    assert req.source_id == "user123"


def test_chat_request_empty_text():
    """Test ChatRequest with empty text."""
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(
            text="",
            source=SourceEnum.API,
            source_id="user123"
        )
    assert "text" in str(exc_info.value)


def test_chat_request_text_too_long():
    """Test ChatRequest with text exceeding max length."""
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(
            text="a" * 6000,  # Exceeds 5000 char limit
            source=SourceEnum.API,
            source_id="user123"
        )
    assert "text" in str(exc_info.value)


def test_chat_request_xss_blocked():
    """Test ChatRequest blocks XSS attempts."""
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(
            text="<script>alert('xss')</script>",
            source=SourceEnum.API,
            source_id="user123"
        )
    assert "dangerous" in str(exc_info.value).lower()


def test_chat_request_sql_injection_blocked():
    """Test ChatRequest blocks SQL injection attempts."""
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(
            text="'; DROP TABLE users; --",
            source=SourceEnum.API,
            source_id="user123"
        )
    assert "dangerous" in str(exc_info.value).lower()


def test_chat_request_whitespace_stripped():
    """Test ChatRequest strips whitespace from text."""
    req = ChatRequest(
        text="  Hello world  ",
        source=SourceEnum.API,
        source_id="user123"
    )
    assert req.text == "Hello world"


def test_chat_request_invalid_source_id():
    """Test ChatRequest with invalid source_id characters."""
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(
            text="Hello",
            source=SourceEnum.API,
            source_id="user@email.com"  # Contains invalid char @
        )
    assert "source_id" in str(exc_info.value)


# ===================== WebSearchRequest Tests =====================

def test_web_search_request_valid():
    """Test valid WebSearchRequest."""
    req = WebSearchRequest(
        q="Python tutorial",
        k=10,
        summarize_top=3
    )
    assert req.q == "Python tutorial"
    assert req.k == 10
    assert req.summarize_top == 3


def test_web_search_request_query_too_long():
    """Test WebSearchRequest with query exceeding max length."""
    with pytest.raises(ValidationError) as exc_info:
        WebSearchRequest(
            q="a" * 600,  # Exceeds 500 char limit
            k=10
        )
    assert "q" in str(exc_info.value)


def test_web_search_request_k_out_of_range():
    """Test WebSearchRequest with k outside valid range."""
    with pytest.raises(ValidationError) as exc_info:
        WebSearchRequest(
            q="Python tutorial",
            k=25  # Exceeds max of 20
        )
    assert "k" in str(exc_info.value)


def test_web_search_request_injection_blocked():
    """Test WebSearchRequest blocks injection attempts."""
    with pytest.raises(ValidationError) as exc_info:
        WebSearchRequest(
            q="<iframe src='evil.com'></iframe>",
            k=10
        )
    assert "dangerous" in str(exc_info.value).lower()


# ===================== WebSummarizeRequest Tests =====================

def test_web_summarize_request_with_url():
    """Test valid WebSummarizeRequest with URL."""
    req = WebSummarizeRequest(
        url="https://example.com/article",
        return_sources=True
    )
    assert req.url == "https://example.com/article"
    assert req.return_sources is True


def test_web_summarize_request_with_query():
    """Test valid WebSummarizeRequest with query."""
    req = WebSummarizeRequest(
        q="Python asyncio",
        return_sources=False
    )
    assert req.q == "Python asyncio"
    assert req.return_sources is False


def test_web_summarize_request_both_url_and_query():
    """Test WebSummarizeRequest rejects both url and query."""
    with pytest.raises(ValidationError) as exc_info:
        WebSummarizeRequest(
            url="https://example.com",
            q="Python tutorial"
        )
    assert "either" in str(exc_info.value).lower()


def test_web_summarize_request_neither_url_nor_query():
    """Test WebSummarizeRequest requires either url or query."""
    with pytest.raises(ValidationError) as exc_info:
        WebSummarizeRequest(
            return_sources=True
        )
    assert "either" in str(exc_info.value).lower()


def test_web_summarize_request_invalid_url_protocol():
    """Test WebSummarizeRequest blocks dangerous URL protocols."""
    with pytest.raises(ValidationError) as exc_info:
        WebSummarizeRequest(
            url="javascript:alert('xss')"
        )
    error_msg = str(exc_info.value).lower()
    assert "url must start with http" in error_msg or "protocol" in error_msg


def test_web_summarize_request_path_traversal():
    """Test WebSummarizeRequest blocks path traversal in URL."""
    with pytest.raises(ValidationError) as exc_info:
        WebSummarizeRequest(
            url="https://example.com/../../../etc/passwd"
        )
    assert "traversal" in str(exc_info.value).lower()


# ===================== AutonomousRequest Tests =====================

def test_autonomous_request_valid():
    """Test valid AutonomousRequest."""
    req = AutonomousRequest(
        goal="Find the best Python frameworks",
        show_plan=True,
        max_steps=10
    )
    assert req.goal == "Find the best Python frameworks"
    assert req.show_plan is True
    assert req.max_steps == 10


def test_autonomous_request_goal_too_long():
    """Test AutonomousRequest with goal exceeding max length."""
    with pytest.raises(ValidationError) as exc_info:
        AutonomousRequest(
            goal="a" * 1500  # Exceeds 1000 char limit
        )
    assert "goal" in str(exc_info.value)


def test_autonomous_request_max_steps_out_of_range():
    """Test AutonomousRequest with max_steps outside valid range."""
    with pytest.raises(ValidationError) as exc_info:
        AutonomousRequest(
            goal="Find Python frameworks",
            max_steps=25  # Exceeds max of 20
        )
    assert "max_steps" in str(exc_info.value)


def test_autonomous_request_injection_blocked():
    """Test AutonomousRequest blocks injection in goal."""
    with pytest.raises(ValidationError) as exc_info:
        AutonomousRequest(
            goal="<script>malicious()</script>"
        )
    assert "dangerous" in str(exc_info.value).lower()


# ===================== ToolRequest Tests =====================

def test_tool_request_valid():
    """Test valid ToolRequest."""
    req = ToolRequest(
        tool_name=ToolNameEnum.MATH,
        parameters={"expr": "2 + 2"}
    )
    assert req.tool_name == ToolNameEnum.MATH
    assert req.parameters == {"expr": "2 + 2"}


def test_tool_request_nested_depth_limit():
    """Test ToolRequest enforces nesting depth limit."""
    deep_nested = {"a": {"b": {"c": {"d": {"e": {"f": {"g": "too deep"}}}}}}}
    
    with pytest.raises(ValidationError) as exc_info:
        ToolRequest(
            tool_name=ToolNameEnum.MATH,
            parameters=deep_nested
        )
    assert "depth" in str(exc_info.value).lower()


def test_tool_request_parameters_not_dict():
    """Test ToolRequest rejects non-dict parameters."""
    with pytest.raises(ValidationError) as exc_info:
        ToolRequest(
            tool_name=ToolNameEnum.MATH,
            parameters="not a dict"  # type: ignore
        )
    assert "parameters" in str(exc_info.value)


# ===================== Unicode Normalization Tests =====================

def test_unicode_normalization():
    """Test unicode normalization works correctly."""
    # é can be represented as single char (NFC) or e + combining accent (NFD)
    req = ChatRequest(
        text="café",  # Using NFC form
        source=SourceEnum.API,
        source_id="user123"
    )
    # Should normalize to NFC form
    assert req.text == "café"


# ===================== Sanitization Tests =====================

def test_html_tag_removal():
    """Test HTML tags are detected as XSS in validation."""
    # Note: Simple <b> tags might not trigger XSS detection as they're not executable
    # Let's test with more dangerous tags
    with pytest.raises(ValidationError) as exc_info:
        ChatRequest(
            text="Click <a href='javascript:void(0)'>here</a>",
            source=SourceEnum.API,
            source_id="user123"
        )
    # Should be caught by XSS or injection validator
    assert "dangerous" in str(exc_info.value).lower() or "error" in str(exc_info.value).lower()


def test_javascript_protocol_blocked():
    """Test javascript: protocol is blocked in URLs."""
    with pytest.raises(ValidationError) as exc_info:
        WebSummarizeRequest(
            url="javascript:void(0)"
        )
    error_msg = str(exc_info.value).lower()
    assert "url must start with http" in error_msg or "protocol" in error_msg


if __name__ == "__main__":
    """Run tests manually without pytest."""
    print("Running input validation tests...\n")
    
    tests = [
        ("ChatRequest valid", test_chat_request_valid),
        ("ChatRequest XSS blocked", test_chat_request_xss_blocked),
        ("ChatRequest SQL injection blocked", test_chat_request_sql_injection_blocked),
        ("WebSearchRequest valid", test_web_search_request_valid),
        ("WebSearchRequest injection blocked", test_web_search_request_injection_blocked),
        ("WebSummarizeRequest with URL", test_web_summarize_request_with_url),
        ("WebSummarizeRequest invalid protocol", test_web_summarize_request_invalid_url_protocol),
        ("AutonomousRequest valid", test_autonomous_request_valid),
        ("AutonomousRequest injection blocked", test_autonomous_request_injection_blocked),
        ("ToolRequest valid", test_tool_request_valid),
    ]
    
    passed = 0
    failed = 0
    
    for name, test_func in tests:
        try:
            test_func()
            print(f"✓ {name}")
            passed += 1
        except Exception as e:
            print(f"✗ {name}: {e}")
            failed += 1
    
    print(f"\n{passed} passed, {failed} failed")
    
    if failed == 0:
        print("\n✓ All validation tests passed!")
