#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/memory_manager.py — Central Memory Management System

Integrates user profile and episodic memory systems.
Provides a single interface for memory operations in chat flow.
"""

import os
import re
import logging
from typing import Dict, List, Any, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# Import memory modules
try:
    from core.user_profile_memory import (
        detect_remember_statement,
        save_user_profile_fact,
        query_user_profile,
        get_all_user_facts,
        DEFAULT_USER_ID,
    )
    USER_PROFILE_AVAILABLE = True
except Exception as e:
    log.warning(f"User profile memory not available: {e}")
    USER_PROFILE_AVAILABLE = False

try:
    from core.episodic_memory import (
        add_to_conversation_buffer,
        summarize_and_save_buffer,
        query_conversation_history,
        get_recent_conversation_summaries,
        get_current_buffer_status,
    )
    EPISODIC_AVAILABLE = True
except Exception as e:
    log.warning(f"Episodic memory not available: {e}")
    EPISODIC_AVAILABLE = False

# Environment configuration
MEMORY_PROFILE_TOP_K = int(os.getenv("MEMORY_PROFILE_TOP_K", "5"))
MEMORY_EPISODIC_TOP_K = int(os.getenv("MEMORY_EPISODIC_TOP_K", "3"))
MEMORY_MAX_CONTEXT_TOKENS = int(os.getenv("MEMORY_MAX_CONTEXT_TOKENS", "800"))

# Secret/sensitive data patterns (basic filtering)
SENSITIVE_PATTERNS = [
    r'\b[A-Za-z0-9]{20,}\b',  # Long alphanumeric strings (potential API keys)
    r'\b(?:password|pwd|passwd|token|secret|api[_-]?key)\s*[:=]\s*\S+',  # Key-value pairs
    r'\b\d{13,19}\b',  # Potential card numbers
    r'\b(?:sk|pk)[-_][a-zA-Z0-9]{20,}\b',  # Stripe-like keys
]


def _contains_sensitive_data(text: str) -> bool:
    """Check if text contains potential secrets."""
    if not text:
        return False
    
    for pattern in SENSITIVE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def _approx_tokens(text: str) -> int:
    """Rough token count estimation."""
    return len(text) // 4


def _trim_to_tokens(text: str, max_tokens: int) -> str:
    """Trim text to approximate token limit."""
    if _approx_tokens(text) <= max_tokens:
        return text
    
    max_chars = max_tokens * 4
    return text[:max_chars]


async def gather_memory_context(
    user_id: str,
    conversation_id: str,
    user_message: str
) -> Dict[str, str]:
    """
    Central function to gather all memory context for a chat request.
    
    Args:
        user_id: User identifier
        conversation_id: Conversation/chat identifier
        user_message: Current user message
        
    Returns:
        Dict with 'profile_context' and 'episodic_context' strings
    """
    result = {
        "profile_context": "",
        "episodic_context": "",
    }
    
    # === USER PROFILE MEMORY ===
    if USER_PROFILE_AVAILABLE:
        try:
            profile_facts = query_user_profile(
                user_id=user_id,
                query_text=user_message,
                top_k=MEMORY_PROFILE_TOP_K
            )
            
            if profile_facts:
                lines = ["User Profile / Known Facts:"]
                for i, fact in enumerate(profile_facts[:MEMORY_PROFILE_TOP_K], 1):
                    text = fact.get("text", "").strip()
                    metadata = fact.get("metadata", {})
                    category = metadata.get("category", "misc")
                    
                    if text:
                        lines.append(f"{i}. [{category}] {text}")
                
                profile_ctx = "\n".join(lines)
                # Trim to fit token budget
                result["profile_context"] = _trim_to_tokens(
                    profile_ctx,
                    MEMORY_MAX_CONTEXT_TOKENS // 2
                )
        except Exception as e:
            log.error(f"Failed to gather profile context: {e}")
    
    # === EPISODIC CONVERSATION MEMORY ===
    if EPISODIC_AVAILABLE:
        try:
            episodic_summaries = query_conversation_history(
                conversation_id=conversation_id,
                query_text=user_message,
                top_k=MEMORY_EPISODIC_TOP_K
            )
            
            if episodic_summaries:
                lines = ["Conversation Context (previous discussion):"]
                for i, summary in enumerate(episodic_summaries[:MEMORY_EPISODIC_TOP_K], 1):
                    text = summary.get("text", "").strip()
                    if text:
                        lines.append(f"• {text}")
                
                episodic_ctx = "\n".join(lines)
                # Trim to fit token budget
                result["episodic_context"] = _trim_to_tokens(
                    episodic_ctx,
                    MEMORY_MAX_CONTEXT_TOKENS // 2
                )
        except Exception as e:
            log.error(f"Failed to gather episodic context: {e}")
    
    return result


async def process_user_message(
    user_id: str,
    conversation_id: str,
    user_message: str
) -> Dict[str, Any]:
    """
    Process user message for memory operations (detect "remember" statements).
    
    Args:
        user_id: User identifier
        conversation_id: Conversation identifier
        user_message: User's message
        
    Returns:
        Dict with processing results
    """
    result = {
        "remember_detected": False,
        "fact_saved": False,
        "fact_id": None,
        "fact_category": None,
        "blocked_sensitive": False,
    }
    
    if not USER_PROFILE_AVAILABLE:
        return result
    
    # Check for "remember" statements
    fact_text = detect_remember_statement(user_message)
    
    if fact_text:
        result["remember_detected"] = True
        
        # Security check: don't save sensitive data
        if _contains_sensitive_data(fact_text):
            log.warning(f"Blocked saving potentially sensitive data: {fact_text[:50]}...")
            result["blocked_sensitive"] = True
            return result
        
        # Save the fact
        fact_id = save_user_profile_fact(
            user_id=user_id,
            fact_text=fact_text
        )
        
        if fact_id:
            result["fact_saved"] = True
            result["fact_id"] = fact_id
            log.info(f"Saved user profile fact from 'remember' statement: {fact_id}")
    
    return result


async def record_conversation_turn(
    conversation_id: str,
    user_message: str,
    assistant_message: str,
    user_id: Optional[str] = None,
    llm_func: Optional[Any] = None
) -> Dict[str, Any]:
    """
    Record a conversation turn and handle automatic summarization.
    
    Args:
        conversation_id: Conversation identifier
        user_message: User's message
        assistant_message: Assistant's response
        user_id: Optional user identifier
        llm_func: Optional LLM function for summarization
        
    Returns:
        Dict with recording results
    """
    result = {
        "recorded": False,
        "summarized": False,
        "summary": None,
    }
    
    if not EPISODIC_AVAILABLE:
        return result
    
    try:
        # Add to buffer
        buffer_result = add_to_conversation_buffer(
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
            user_id=user_id
        )
        
        result["recorded"] = buffer_result.get("added", False)
        
        # Check if summarization needed
        if buffer_result.get("needs_summarization"):
            log.info(f"Conversation buffer threshold reached for {conversation_id}, summarizing...")
            
            summary = await summarize_and_save_buffer(
                conversation_id=conversation_id,
                user_id=user_id,
                llm_func=llm_func
            )
            
            if summary:
                result["summarized"] = True
                result["summary"] = summary
                log.info(f"Saved conversation summary for {conversation_id}")
        
        return result
        
    except Exception as e:
        log.error(f"Failed to record conversation turn: {e}")
        return result


def get_memory_stats(user_id: Optional[str] = None, conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """
    Get memory system statistics.
    
    Args:
        user_id: Optional user identifier
        conversation_id: Optional conversation identifier
        
    Returns:
        Dict with memory statistics
    """
    stats = {
        "profile_memory": {
            "enabled": USER_PROFILE_AVAILABLE,
            "facts_count": 0,
        },
        "episodic_memory": {
            "enabled": EPISODIC_AVAILABLE,
            "summaries_count": 0,
            "buffer_status": {},
        },
    }
    
    # User profile stats
    if USER_PROFILE_AVAILABLE and user_id:
        try:
            facts = get_all_user_facts(user_id)
            stats["profile_memory"]["facts_count"] = len(facts)
            
            # Count by category
            categories = {}
            for fact in facts:
                cat = fact.get("metadata", {}).get("category", "misc")
                categories[cat] = categories.get(cat, 0) + 1
            stats["profile_memory"]["by_category"] = categories
        except Exception as e:
            log.error(f"Failed to get profile stats: {e}")
    
    # Episodic memory stats
    if EPISODIC_AVAILABLE and conversation_id:
        try:
            summaries = get_recent_conversation_summaries(conversation_id, limit=100)
            stats["episodic_memory"]["summaries_count"] = len(summaries)
            
            buffer_status = get_current_buffer_status(conversation_id)
            stats["episodic_memory"]["buffer_status"] = buffer_status
        except Exception as e:
            log.error(f"Failed to get episodic stats: {e}")
    
    return stats
