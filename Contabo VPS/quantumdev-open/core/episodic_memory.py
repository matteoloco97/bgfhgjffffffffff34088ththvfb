#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/episodic_memory.py — Episodic Conversation Memory System

Manages conversation history summaries per chat/session.
- Rolling buffer of recent messages
- Automatic summarization when threshold reached
- Semantic retrieval of past conversation context
"""

import os
import time
import hashlib
import logging
from typing import Dict, List, Any, Optional, Tuple
from collections import deque
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# Environment configuration
EPISODIC_COLLECTION = os.getenv("EPISODIC_MEMORY_COLLECTION", "conversation_history")
EPISODIC_ENABLED = os.getenv("EPISODIC_MEMORY_ENABLED", "1").strip() in ("1", "true", "yes", "on")

# Buffer and summarization thresholds
EPISODIC_BUFFER_SIZE = int(os.getenv("EPISODIC_BUFFER_SIZE", "10"))  # max messages before summarization
EPISODIC_BUFFER_TOKEN_LIMIT = int(os.getenv("EPISODIC_BUFFER_TOKEN_LIMIT", "2000"))  # token-based threshold
EPISODIC_SUMMARIZE_ENABLED = os.getenv("EPISODIC_SUMMARIZE_ENABLED", "1").strip() in ("1", "true", "yes", "on")
EPISODIC_MAX_AGE_DAYS = int(os.getenv("EPISODIC_MAX_AGE_DAYS", "90"))

# In-memory buffers per conversation (session-based, not persistent)
_conversation_buffers: Dict[str, deque] = {}


def _get_chroma_collection():
    """Get or create episodic memory ChromaDB collection."""
    try:
        from utils.chroma_handler import _col
        return _col(EPISODIC_COLLECTION)
    except Exception as e:
        log.error(f"Failed to get episodic collection: {e}")
        return None


def _approx_tokens(text: str) -> int:
    """Rough token count estimation."""
    return len(text) // 4


def _get_conversation_buffer(conversation_id: str) -> deque:
    """Get or create conversation buffer."""
    if conversation_id not in _conversation_buffers:
        _conversation_buffers[conversation_id] = deque(maxlen=EPISODIC_BUFFER_SIZE)
    return _conversation_buffers[conversation_id]


def add_to_conversation_buffer(
    conversation_id: str,
    user_message: str,
    assistant_message: str,
    user_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add a turn (user + assistant message) to the conversation buffer.
    
    Args:
        conversation_id: Conversation/chat identifier
        user_message: User's message
        assistant_message: Assistant's response
        user_id: Optional user identifier
        
    Returns:
        Dict with status and potentially a summary if threshold reached
    """
    if not EPISODIC_ENABLED:
        return {"added": False, "reason": "episodic_memory_disabled"}
    
    if not conversation_id:
        log.warning("Cannot add to buffer without conversation_id")
        return {"added": False, "reason": "missing_conversation_id"}
    
    buffer = _get_conversation_buffer(conversation_id)
    
    # Add turn to buffer
    turn = {
        "timestamp": int(time.time()),
        "user": user_message,
        "assistant": assistant_message,
    }
    buffer.append(turn)
    
    result = {
        "added": True,
        "buffer_size": len(buffer),
        "needs_summarization": False,
    }
    
    # Check if we need to summarize
    if EPISODIC_SUMMARIZE_ENABLED and len(buffer) >= EPISODIC_BUFFER_SIZE:
        # Estimate total tokens in buffer
        total_tokens = sum(
            _approx_tokens(t["user"]) + _approx_tokens(t["assistant"])
            for t in buffer
        )
        
        if total_tokens >= EPISODIC_BUFFER_TOKEN_LIMIT:
            result["needs_summarization"] = True
            result["total_tokens"] = total_tokens
    
    return result


async def summarize_and_save_buffer(
    conversation_id: str,
    user_id: Optional[str] = None,
    llm_func: Optional[Any] = None
) -> Optional[str]:
    """
    Summarize current conversation buffer and save to ChromaDB.
    
    Args:
        conversation_id: Conversation identifier
        user_id: Optional user identifier
        llm_func: Optional LLM function for summarization (async)
        
    Returns:
        Summary text if successful, None otherwise
    """
    if not EPISODIC_ENABLED or not EPISODIC_SUMMARIZE_ENABLED:
        return None
    
    buffer = _get_conversation_buffer(conversation_id)
    if len(buffer) == 0:
        return None
    
    col = _get_chroma_collection()
    if col is None:
        return None
    
    try:
        # Build context from buffer
        turns = []
        for i, turn in enumerate(buffer, 1):
            turns.append(f"Turn {i}:")
            turns.append(f"User: {turn['user']}")
            turns.append(f"Assistant: {turn['assistant']}")
        
        context = "\n".join(turns)
        
        # Generate summary
        summary = None
        if llm_func:
            try:
                prompt = (
                    "Riassumi questa conversazione in 2-4 frasi chiave, "
                    "mantenendo i punti principali discussi e le decisioni prese.\n\n"
                    f"{context}"
                )
                
                # Simple persona for summarization
                persona = "Sei un assistente che crea riassunti concisi e accurati."
                
                summary = await llm_func(prompt, persona)
            except Exception as e:
                log.warning(f"LLM summarization failed: {e}")
        
        # Fallback: rule-based summary
        if not summary:
            topics = []
            for turn in buffer:
                # Extract first few words from each user message
                words = turn["user"].split()[:8]
                if words:
                    topics.append(" ".join(words) + "...")
            
            summary = "Conversazione su: " + " | ".join(topics[:3])
        
        # Save to ChromaDB
        timestamp_ms = int(time.time() * 1000)
        doc_id = f"conv:{conversation_id}:{timestamp_ms}"
        
        metadata = {
            "conversation_id": conversation_id,
            "created_at": int(time.time()),
            "turns_count": len(buffer),
        }
        
        if user_id:
            metadata["user_id"] = user_id
        
        col.add(
            ids=[doc_id],
            documents=[summary],
            metadatas=[metadata]
        )
        
        log.info(f"Saved conversation summary: {doc_id} ({len(buffer)} turns)")
        
        # Clear buffer after successful save
        buffer.clear()
        
        return summary
        
    except Exception as e:
        log.error(f"Failed to summarize and save buffer: {e}")
        return None


def query_conversation_history(
    conversation_id: str,
    query_text: str,
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """
    Query past conversation summaries for this conversation.
    
    Args:
        conversation_id: Conversation identifier
        query_text: Query text for semantic search
        top_k: Number of results to return
        
    Returns:
        List of matching summaries
    """
    if not EPISODIC_ENABLED:
        return []
    
    col = _get_chroma_collection()
    if col is None:
        return []
    
    try:
        results = col.query(
            query_texts=[query_text],
            n_results=top_k,
            where={"conversation_id": conversation_id},
            include=["documents", "metadatas", "distances"]
        )
        
        summaries = []
        if results and results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                summary = {
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i] if results.get("documents") else "",
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "distance": results["distances"][0][i] if results.get("distances") else 1.0,
                }
                summaries.append(summary)
        
        return summaries
        
    except Exception as e:
        log.error(f"Failed to query conversation history: {e}")
        return []


def get_recent_conversation_summaries(
    conversation_id: str,
    limit: int = 10
) -> List[Dict[str, Any]]:
    """
    Get recent summaries for a conversation (chronological order).
    
    Args:
        conversation_id: Conversation identifier
        limit: Maximum number of summaries
        
    Returns:
        List of recent summaries
    """
    if not EPISODIC_ENABLED:
        return []
    
    col = _get_chroma_collection()
    if col is None:
        return []
    
    try:
        results = col.get(
            where={"conversation_id": conversation_id},
            limit=limit,
            include=["documents", "metadatas"]
        )
        
        summaries = []
        if results and results.get("ids"):
            for i, doc_id in enumerate(results["ids"]):
                summary = {
                    "id": doc_id,
                    "text": results["documents"][i] if i < len(results.get("documents", [])) else "",
                    "metadata": results["metadatas"][i] if i < len(results.get("metadatas", [])) else {},
                }
                summaries.append(summary)
        
        # Sort by created_at (most recent first)
        summaries.sort(
            key=lambda x: x.get("metadata", {}).get("created_at", 0),
            reverse=True
        )
        
        return summaries
        
    except Exception as e:
        log.error(f"Failed to get recent summaries: {e}")
        return []


def get_current_buffer_status(conversation_id: str) -> Dict[str, Any]:
    """
    Get status of current conversation buffer.
    
    Args:
        conversation_id: Conversation identifier
        
    Returns:
        Dict with buffer status
    """
    if conversation_id not in _conversation_buffers:
        return {
            "exists": False,
            "size": 0,
            "max_size": EPISODIC_BUFFER_SIZE,
        }
    
    buffer = _conversation_buffers[conversation_id]
    total_tokens = sum(
        _approx_tokens(t["user"]) + _approx_tokens(t["assistant"])
        for t in buffer
    )
    
    return {
        "exists": True,
        "size": len(buffer),
        "max_size": EPISODIC_BUFFER_SIZE,
        "estimated_tokens": total_tokens,
        "token_limit": EPISODIC_BUFFER_TOKEN_LIMIT,
        "needs_summarization": total_tokens >= EPISODIC_BUFFER_TOKEN_LIMIT,
    }


def clear_conversation_buffer(conversation_id: str) -> bool:
    """
    Clear conversation buffer without saving.
    
    Args:
        conversation_id: Conversation identifier
        
    Returns:
        True if buffer existed and was cleared
    """
    if conversation_id in _conversation_buffers:
        _conversation_buffers[conversation_id].clear()
        log.info(f"Cleared conversation buffer: {conversation_id}")
        return True
    return False


def cleanup_old_episodes(conversation_id: Optional[str] = None, days: int = EPISODIC_MAX_AGE_DAYS) -> int:
    """
    Clean up old episodic memories.
    
    Args:
        conversation_id: Optional specific conversation to clean (None = all)
        days: Maximum age in days
        
    Returns:
        Number of episodes deleted
    """
    col = _get_chroma_collection()
    if col is None:
        return 0
    
    try:
        threshold = int(time.time()) - (days * 86400)
        
        # Build where filter
        where_filter = {}
        if conversation_id:
            where_filter["conversation_id"] = conversation_id
        
        # Get episodes
        results = col.get(
            where=where_filter if where_filter else None,
            include=["metadatas"]
        )
        
        if not results or not results.get("ids"):
            return 0
        
        # Find old episodes
        old_ids = []
        for i, episode_id in enumerate(results["ids"]):
            metadata = results["metadatas"][i] if i < len(results.get("metadatas", [])) else {}
            created_at = metadata.get("created_at", 0)
            if created_at and created_at < threshold:
                old_ids.append(episode_id)
        
        if old_ids:
            col.delete(ids=old_ids)
            log.info(f"Cleaned up {len(old_ids)} old episodic memories")
        
        return len(old_ids)
        
    except Exception as e:
        log.error(f"Failed to cleanup old episodes: {e}")
        return 0
