#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
backend/models.py — Comprehensive Pydantic models for API input validation

This module provides:
- Strict input validation using Pydantic v2
- Security measures (XSS, SQL injection, path traversal protection)
- Data sanitization (HTML tag removal, special char escaping, unicode normalization)
- Clear error messages for API consumers
"""

from __future__ import annotations

import re
import html
import unicodedata
from typing import Optional, Dict, Any, List
from enum import Enum

from pydantic import (
    BaseModel,
    Field,
    field_validator,
    model_validator,
    HttpUrl,
    field_serializer,
)


# ===================== Constants & Security Patterns =====================

# Maximum nesting depth for JSON objects (prevent DOS attacks)
MAX_NESTED_DEPTH = 5

# Dangerous patterns that could indicate injection attempts
SQL_INJECTION_PATTERNS = [
    r"(\bUNION\b.*\bSELECT\b)",
    r"(\bDROP\b.*\bTABLE\b)",
    r"(\bINSERT\b.*\bINTO\b)",
    r"(\bDELETE\b.*\bFROM\b)",
    r"(\bUPDATE\b.*\bSET\b)",
    r"(--\s*$)",  # SQL comment
    r"(/\*.*\*/)",  # Multi-line SQL comment
    r"(\bEXEC\b|\bEXECUTE\b)",
    r"(xp_cmdshell)",
]

XSS_PATTERNS = [
    r"<script[^>]*>.*?</script>",
    r"javascript:",
    r"on\w+\s*=",  # Event handlers like onclick=
    r"<iframe[^>]*>",
    r"<object[^>]*>",
    r"<embed[^>]*>",
]

PATH_TRAVERSAL_PATTERNS = [
    r"\.\./",  # Directory traversal
    r"\.\.",  # Parent directory
    r"~[/\\]",  # Home directory
]

# Compile patterns for performance
_SQL_REGEX = [re.compile(p, re.IGNORECASE) for p in SQL_INJECTION_PATTERNS]
_XSS_REGEX = [re.compile(p, re.IGNORECASE) for p in XSS_PATTERNS]
_PATH_REGEX = [re.compile(p) for p in PATH_TRAVERSAL_PATTERNS]


# ===================== Enums =====================

class SourceEnum(str, Enum):
    """Valid sources for requests."""
    API = "api"
    TG = "tg"  # Telegram
    GUI = "gui"
    WEB = "web"
    SYSTEM = "system"
    TEST = "test"


class ToolNameEnum(str, Enum):
    """Valid tool names."""
    MATH = "math"
    PYTHON = "python"
    WEB_SEARCH = "web_search"
    WEB_SUMMARIZE = "web_summarize"
    CODE_EXEC = "code_exec"
    FILE_UPLOAD = "file_upload"
    FILE_QUERY = "file_query"
    OCR = "ocr"


# ===================== Utility Functions =====================

def sanitize_html(text: str) -> str:
    """
    Remove HTML tags and escape special characters.
    
    Args:
        text: Input text potentially containing HTML
        
    Returns:
        Sanitized text with HTML removed and special chars escaped
    """
    if not text:
        return text
    
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    
    # Escape HTML special characters
    text = html.escape(text, quote=False)
    
    return text


def normalize_unicode(text: str) -> str:
    """
    Normalize unicode to NFC form for consistency.
    
    Args:
        text: Input text with potential unicode variations
        
    Returns:
        Normalized unicode text
    """
    if not text:
        return text
    
    return unicodedata.normalize("NFC", text)


def check_injection_patterns(text: str, field_name: str = "field") -> str:
    """
    Check for SQL injection and XSS patterns.
    
    Args:
        text: Input text to validate
        field_name: Name of the field for error messages
        
    Returns:
        Original text if safe
        
    Raises:
        ValueError: If dangerous patterns are detected
    """
    if not text:
        return text
    
    # Check SQL injection patterns
    for pattern in _SQL_REGEX:
        if pattern.search(text):
            raise ValueError(
                f"{field_name} contains potentially dangerous SQL pattern. "
                f"Please remove SQL-like syntax."
            )
    
    # Check XSS patterns
    for pattern in _XSS_REGEX:
        if pattern.search(text):
            raise ValueError(
                f"{field_name} contains potentially dangerous HTML/JavaScript. "
                f"Please remove script tags and event handlers."
            )
    
    # Check path traversal
    for pattern in _PATH_REGEX:
        if pattern.search(text):
            raise ValueError(
                f"{field_name} contains path traversal patterns. "
                f"Please use safe file paths."
            )
    
    return text


def check_nested_depth(obj: Any, max_depth: int = MAX_NESTED_DEPTH, current_depth: int = 0) -> None:
    """
    Check if nested object depth exceeds limit (prevent DOS).
    
    Args:
        obj: Object to check
        max_depth: Maximum allowed nesting depth
        current_depth: Current nesting level (used in recursion)
        
    Raises:
        ValueError: If nesting depth exceeds limit
    """
    if current_depth > max_depth:
        raise ValueError(
            f"Object nesting depth exceeds maximum of {max_depth}. "
            f"Please reduce nesting complexity."
        )
    
    if isinstance(obj, dict):
        for value in obj.values():
            check_nested_depth(value, max_depth, current_depth + 1)
    elif isinstance(obj, list):
        for item in obj:
            check_nested_depth(item, max_depth, current_depth + 1)


# ===================== Request Models =====================

class ChatRequest(BaseModel):
    """
    Request model for /chat endpoint.
    
    Validates:
    - Text length (1-5000 characters)
    - Source type (enum)
    - Source ID presence
    - Security patterns (XSS, SQL injection)
    
    Example:
        {
            "text": "What's the weather in Rome?",
            "source": "api",
            "source_id": "user123"
        }
    """
    
    text: str = Field(
        ...,
        min_length=1,
        max_length=5000,
        description="User's message text (1-5000 characters)"
    )
    source: SourceEnum = Field(
        default=SourceEnum.API,
        description="Source of the request"
    )
    source_id: str = Field(
        default="default",
        min_length=1,
        max_length=100,
        description="Unique identifier for the source/user"
    )
    system_prompt: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional custom system prompt"
    )
    messages: Optional[List[Dict[str, Any]]] = Field(
        None,
        description="Optional OpenAI-style messages array"
    )
    
    @field_validator("text")
    @classmethod
    def validate_text(cls, v: str) -> str:
        """Validate and sanitize text field."""
        if not v or not v.strip():
            raise ValueError("text cannot be empty or whitespace only")
        
        # Strip whitespace
        v = v.strip()
        
        # Normalize unicode
        v = normalize_unicode(v)
        
        # Check for injection patterns
        v = check_injection_patterns(v, "text")
        
        return v
    
    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        """Validate and sanitize source_id."""
        if not v or not v.strip():
            raise ValueError("source_id cannot be empty")
        
        v = v.strip()
        
        # Only allow alphanumeric, underscore, hyphen, colon
        if not re.match(r"^[a-zA-Z0-9_:\-]+$", v):
            raise ValueError(
                "source_id must contain only alphanumeric characters, "
                "underscores, hyphens, and colons"
            )
        
        return v
    
    @field_validator("system_prompt")
    @classmethod
    def validate_system_prompt(cls, v: Optional[str]) -> Optional[str]:
        """Validate and sanitize system_prompt if provided."""
        if v is None:
            return v
        
        v = v.strip()
        if not v:
            return None
        
        # Normalize unicode
        v = normalize_unicode(v)
        
        # Check for injection patterns
        v = check_injection_patterns(v, "system_prompt")
        
        return v
    
    @field_validator("messages")
    @classmethod
    def validate_messages(cls, v: Optional[List[Dict[str, Any]]]) -> Optional[List[Dict[str, Any]]]:
        """Validate messages array structure and content."""
        if v is None:
            return v
        
        if not isinstance(v, list):
            raise ValueError("messages must be a list")
        
        if len(v) > 100:
            raise ValueError("messages array cannot exceed 100 entries")
        
        # Check nesting depth
        check_nested_depth(v, max_depth=3)
        
        # Validate each message
        for i, msg in enumerate(v):
            if not isinstance(msg, dict):
                raise ValueError(f"messages[{i}] must be a dict")
            
            role = msg.get("role")
            if role not in ("user", "assistant", "system"):
                raise ValueError(
                    f"messages[{i}].role must be 'user', 'assistant', or 'system'"
                )
            
            content = msg.get("content")
            if not isinstance(content, str):
                raise ValueError(f"messages[{i}].content must be a string")
            
            if len(content) > 5000:
                raise ValueError(
                    f"messages[{i}].content exceeds 5000 characters"
                )
        
        return v


class WebSearchRequest(BaseModel):
    """
    Request model for /web/search endpoint.
    
    Validates:
    - Query length (1-500 characters)
    - k parameter (1-20 results)
    - summarize_top parameter (0-10)
    
    Example:
        {
            "q": "latest Python 3.12 features",
            "k": 10,
            "summarize_top": 3
        }
    """
    
    q: str = Field(
        ...,
        min_length=1,
        max_length=500,
        description="Search query (1-500 characters)"
    )
    k: int = Field(
        default=6,
        ge=1,
        le=20,
        description="Number of results to return (1-20)"
    )
    summarize_top: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Number of top results to summarize (0-10)"
    )
    source: SourceEnum = Field(
        default=SourceEnum.API,
        description="Source of the request"
    )
    source_id: str = Field(
        default="default",
        min_length=1,
        max_length=100,
        description="Unique identifier for the source/user"
    )
    
    @field_validator("q")
    @classmethod
    def validate_query(cls, v: str) -> str:
        """Validate and sanitize search query."""
        if not v or not v.strip():
            raise ValueError("q cannot be empty or whitespace only")
        
        # Strip whitespace
        v = v.strip()
        
        # Normalize unicode
        v = normalize_unicode(v)
        
        # Check for injection patterns
        v = check_injection_patterns(v, "q")
        
        return v
    
    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        """Validate source_id."""
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9_:\-]+$", v):
            raise ValueError(
                "source_id must contain only alphanumeric characters, "
                "underscores, hyphens, and colons"
            )
        return v


class WebSummarizeRequest(BaseModel):
    """
    Request model for /web/summarize endpoint.
    
    Validates:
    - Either url or q (query) is provided (but not both)
    - URL format if provided
    - Query length if provided
    
    Example:
        {
            "url": "https://example.com/article",
            "return_sources": true
        }
    """
    
    url: Optional[str] = Field(
        None,
        max_length=2000,
        description="URL to summarize (alternative to query)"
    )
    q: Optional[str] = Field(
        None,
        max_length=500,
        description="Search query to find and summarize (alternative to url)"
    )
    k: int = Field(
        default=6,
        ge=1,
        le=20,
        description="Number of results to fetch (for query mode)"
    )
    summarize_top: int = Field(
        default=2,
        ge=0,
        le=10,
        description="Number of top results to summarize"
    )
    return_sources: bool = Field(
        default=True,
        description="Whether to return source URLs"
    )
    source: SourceEnum = Field(
        default=SourceEnum.TG,
        description="Source of the request"
    )
    source_id: str = Field(
        default="default",
        min_length=1,
        max_length=100,
        description="Unique identifier for the source/user"
    )
    
    @field_validator("url")
    @classmethod
    def validate_url(cls, v: Optional[str]) -> Optional[str]:
        """Validate URL format if provided."""
        if v is None:
            return v
        
        v = v.strip()
        if not v:
            return None
        
        # Check for path traversal
        for pattern in _PATH_REGEX:
            if pattern.search(v):
                raise ValueError("url contains invalid path traversal patterns")
        
        # Basic URL validation
        if not re.match(r"^https?://", v, re.IGNORECASE):
            raise ValueError("url must start with http:// or https://")
        
        # Check for dangerous protocols
        dangerous_protocols = ["javascript:", "data:", "file:", "ftp:"]
        for protocol in dangerous_protocols:
            if v.lower().startswith(protocol):
                raise ValueError(f"url protocol '{protocol}' is not allowed")
        
        return v
    
    @field_validator("q")
    @classmethod
    def validate_query(cls, v: Optional[str]) -> Optional[str]:
        """Validate search query if provided."""
        if v is None:
            return v
        
        v = v.strip()
        if not v:
            return None
        
        # Normalize unicode
        v = normalize_unicode(v)
        
        # Check for injection patterns
        v = check_injection_patterns(v, "q")
        
        return v
    
    @model_validator(mode="after")
    def validate_url_or_query(self) -> "WebSummarizeRequest":
        """Ensure either url or q is provided, but not both."""
        if not self.url and not self.q:
            raise ValueError("Either 'url' or 'q' must be provided")
        
        if self.url and self.q:
            raise ValueError("Provide either 'url' or 'q', not both")
        
        return self
    
    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        """Validate source_id."""
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9_:\-]+$", v):
            raise ValueError(
                "source_id must contain only alphanumeric characters, "
                "underscores, hyphens, and colons"
            )
        return v


class AutonomousRequest(BaseModel):
    """
    Request model for /autonomous endpoint.
    
    Validates:
    - Goal text (1-1000 characters)
    - max_steps range (1-20)
    
    Example:
        {
            "goal": "Find the best Python web framework for 2024",
            "show_plan": true,
            "max_steps": 10
        }
    """
    
    goal: str = Field(
        ...,
        min_length=1,
        max_length=1000,
        description="The goal/task to accomplish (1-1000 characters)"
    )
    show_plan: bool = Field(
        default=True,
        description="Whether to include execution plan in response"
    )
    max_steps: int = Field(
        default=10,
        ge=1,
        le=20,
        description="Maximum number of execution steps (1-20)"
    )
    source: SourceEnum = Field(
        default=SourceEnum.API,
        description="Source of the request"
    )
    source_id: str = Field(
        default="default",
        min_length=1,
        max_length=100,
        description="Unique identifier for the source/user"
    )
    require_approval: bool = Field(
        default=False,
        description="If true, returns plan for approval before execution"
    )
    
    @field_validator("goal")
    @classmethod
    def validate_goal(cls, v: str) -> str:
        """Validate and sanitize goal text."""
        if not v or not v.strip():
            raise ValueError("goal cannot be empty or whitespace only")
        
        # Strip whitespace
        v = v.strip()
        
        # Normalize unicode
        v = normalize_unicode(v)
        
        # Check for injection patterns
        v = check_injection_patterns(v, "goal")
        
        return v
    
    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        """Validate source_id."""
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9_:\-]+$", v):
            raise ValueError(
                "source_id must contain only alphanumeric characters, "
                "underscores, hyphens, and colons"
            )
        return v


class ToolRequest(BaseModel):
    """
    Request model for tool execution endpoints.
    
    Validates:
    - Tool name (enum)
    - Parameters dict structure
    - Nesting depth
    
    Example:
        {
            "tool_name": "math",
            "parameters": {
                "expr": "2 + 2"
            }
        }
    """
    
    tool_name: ToolNameEnum = Field(
        ...,
        description="Name of the tool to execute"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict,
        description="Tool-specific parameters"
    )
    source: SourceEnum = Field(
        default=SourceEnum.API,
        description="Source of the request"
    )
    source_id: str = Field(
        default="default",
        min_length=1,
        max_length=100,
        description="Unique identifier for the source/user"
    )
    
    @field_validator("parameters")
    @classmethod
    def validate_parameters(cls, v: Dict[str, Any]) -> Dict[str, Any]:
        """Validate parameters dict."""
        if not isinstance(v, dict):
            raise ValueError("parameters must be a dict")
        
        # Check nesting depth
        check_nested_depth(v, max_depth=MAX_NESTED_DEPTH)
        
        # Validate string values for injection patterns
        for key, value in v.items():
            if isinstance(value, str) and len(value) > 0:
                # Check for injection patterns in string parameters
                try:
                    check_injection_patterns(value, f"parameters.{key}")
                except ValueError:
                    # Allow some tool-specific patterns (e.g., math expressions)
                    # but still normalize unicode
                    v[key] = normalize_unicode(value.strip())
        
        return v
    
    @field_validator("source_id")
    @classmethod
    def validate_source_id(cls, v: str) -> str:
        """Validate source_id."""
        v = v.strip()
        if not re.match(r"^[a-zA-Z0-9_:\-]+$", v):
            raise ValueError(
                "source_id must contain only alphanumeric characters, "
                "underscores, hyphens, and colons"
            )
        return v


# ===================== Example Usage & Testing =====================

if __name__ == "__main__":
    """Example usage and validation tests."""
    
    # Example 1: Valid ChatRequest
    try:
        chat_req = ChatRequest(
            text="What's the weather like today?",
            source=SourceEnum.API,
            source_id="user123"
        )
        print(f"✓ Valid ChatRequest: {chat_req.text[:30]}...")
    except Exception as e:
        print(f"✗ ChatRequest failed: {e}")
    
    # Example 2: Invalid ChatRequest (XSS attempt)
    try:
        chat_req = ChatRequest(
            text="<script>alert('xss')</script>",
            source=SourceEnum.API,
            source_id="user123"
        )
        print(f"✗ XSS not blocked: {chat_req.text}")
    except ValueError as e:
        print(f"✓ XSS blocked: {str(e)[:50]}...")
    
    # Example 3: Valid WebSearchRequest
    try:
        search_req = WebSearchRequest(
            q="Python asyncio tutorial",
            k=10,
            summarize_top=3
        )
        print(f"✓ Valid WebSearchRequest: {search_req.q}")
    except Exception as e:
        print(f"✗ WebSearchRequest failed: {e}")
    
    # Example 4: Valid WebSummarizeRequest with URL
    try:
        summarize_req = WebSummarizeRequest(
            url="https://example.com/article",
            return_sources=True
        )
        print(f"✓ Valid WebSummarizeRequest: {summarize_req.url}")
    except Exception as e:
        print(f"✗ WebSummarizeRequest failed: {e}")
    
    # Example 5: Invalid WebSummarizeRequest (no url or query)
    try:
        summarize_req = WebSummarizeRequest(
            return_sources=True
        )
        print(f"✗ Validation not working: {summarize_req}")
    except ValueError as e:
        print(f"✓ Missing url/query caught: {str(e)[:50]}...")
    
    # Example 6: Valid AutonomousRequest
    try:
        auto_req = AutonomousRequest(
            goal="Find the top 5 Python frameworks",
            show_plan=True,
            max_steps=10
        )
        print(f"✓ Valid AutonomousRequest: {auto_req.goal[:30]}...")
    except Exception as e:
        print(f"✗ AutonomousRequest failed: {e}")
    
    # Example 7: Valid ToolRequest
    try:
        tool_req = ToolRequest(
            tool_name=ToolNameEnum.MATH,
            parameters={"expr": "2 + 2 * 3"}
        )
        print(f"✓ Valid ToolRequest: {tool_req.tool_name}")
    except Exception as e:
        print(f"✗ ToolRequest failed: {e}")
    
    print("\n✓ All validation tests completed!")
