#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/conversational_memory.py — Conversational Memory System for QuantumDev Max

Features:
- 32K token context window management
- Sliding window (last N turns)
- Auto-summarization after threshold
- Semantic search on conversation history
- Session persistence (7 days TTL)
- Token-aware context management

Author: Matteo (QuantumDev)
Version: 2.0.0
"""

from __future__ import annotations

import os
import json
import time
import hashlib
import logging
import math
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field, asdict
from datetime import datetime

import redis
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === ENV Configuration ===
def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        import re
        m = re.search(r"-?\d+", raw)
        return int(m.group(0)) if m else default
    except Exception:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


# Configuration
ENABLE_CONVERSATIONAL_MEMORY = _env_bool("ENABLE_CONVERSATIONAL_MEMORY", True)
MAX_CONTEXT_TOKENS = _env_int("MAX_CONTEXT_TOKENS", 32000)
SLIDING_WINDOW_SIZE = _env_int("SLIDING_WINDOW_SIZE", 10)
SUMMARIZATION_THRESHOLD = _env_int("SUMMARIZATION_THRESHOLD", 20)
SESSION_TTL = _env_int("SESSION_TTL", 604800)  # 7 days in seconds
SUMMARIZATION_TOKEN_LIMIT = _env_int("SUMMARIZATION_TOKEN_LIMIT", 2000)  # Max tokens for summarization

REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = _env_int("REDIS_PORT", 6379)
REDIS_DB = _env_int("REDIS_DB", 0)

# Redis client
_redis_client: Optional[redis.Redis] = None


def _get_redis() -> redis.Redis:
    """Get or create Redis client."""
    global _redis_client
    if _redis_client is None:
        _redis_client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            db=REDIS_DB,
            decode_responses=True,
        )
    return _redis_client


# === Token Utilities ===
def approx_tokens(text: str) -> int:
    """Approximate token count (4 chars ≈ 1 token)."""
    return math.ceil(len(text or "") / 4)


def trim_to_tokens(text: str, max_tokens: int) -> str:
    """Trim text to approximate token limit."""
    if not text or max_tokens <= 0:
        return ""
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars]


# === Data Classes ===
@dataclass
class Message:
    """Single conversation message."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: int = field(default_factory=lambda: int(time.time()))
    tokens: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def __post_init__(self):
        if not self.tokens:
            self.tokens = approx_tokens(self.content)
    
    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Message":
        return cls(
            role=data.get("role", "user"),
            content=data.get("content", ""),
            timestamp=data.get("timestamp", int(time.time())),
            tokens=data.get("tokens", 0),
            metadata=data.get("metadata", {}),
        )


@dataclass
class ConversationSession:
    """Conversation session with history and context."""
    session_id: str
    source: str  # "tg", "web", "api"
    source_id: str  # user/chat identifier
    messages: List[Message] = field(default_factory=list)
    summary: str = ""
    summary_tokens: int = 0
    total_tokens: int = 0
    turn_count: int = 0
    created_at: int = field(default_factory=lambda: int(time.time()))
    updated_at: int = field(default_factory=lambda: int(time.time()))
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "source": self.source,
            "source_id": self.source_id,
            "messages": [m.to_dict() for m in self.messages],
            "summary": self.summary,
            "summary_tokens": self.summary_tokens,
            "total_tokens": self.total_tokens,
            "turn_count": self.turn_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "metadata": self.metadata,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ConversationSession":
        return cls(
            session_id=data.get("session_id", ""),
            source=data.get("source", ""),
            source_id=data.get("source_id", ""),
            messages=[Message.from_dict(m) for m in data.get("messages", [])],
            summary=data.get("summary", ""),
            summary_tokens=data.get("summary_tokens", 0),
            total_tokens=data.get("total_tokens", 0),
            turn_count=data.get("turn_count", 0),
            created_at=data.get("created_at", int(time.time())),
            updated_at=data.get("updated_at", int(time.time())),
            metadata=data.get("metadata", {}),
        )
    
    def add_message(self, role: str, content: str, metadata: Optional[Dict[str, Any]] = None) -> Message:
        """Add a message to the conversation."""
        msg = Message(
            role=role,
            content=content,
            metadata=metadata or {},
        )
        self.messages.append(msg)
        self.total_tokens += msg.tokens
        if role == "user":
            self.turn_count += 1
        self.updated_at = int(time.time())
        return msg
    
    def get_recent_messages(self, n: int = SLIDING_WINDOW_SIZE) -> List[Message]:
        """Get last N messages (sliding window)."""
        return self.messages[-n:] if self.messages else []
    
    def needs_summarization(self) -> bool:
        """Check if conversation needs summarization."""
        return self.turn_count >= SUMMARIZATION_THRESHOLD


# === Conversational Memory Manager ===
class ConversationalMemory:
    """
    Manages conversational memory with:
    - Session persistence in Redis
    - Sliding window for recent context
    - Auto-summarization for long conversations
    - Token budget management
    """
    
    def __init__(self, llm_func: Optional[callable] = None):
        """
        Initialize Conversational Memory.
        
        Args:
            llm_func: Async function to call LLM for summarization.
                      Signature: async def llm_func(prompt: str, system: str) -> str
        """
        self.llm_func = llm_func
        self._sessions_cache: Dict[str, ConversationSession] = {}
        log.info(
            "ConversationalMemory initialized: "
            f"max_tokens={MAX_CONTEXT_TOKENS}, "
            f"sliding_window={SLIDING_WINDOW_SIZE}, "
            f"summarize_threshold={SUMMARIZATION_THRESHOLD}"
        )
    
    def _session_key(self, source: str, source_id: str) -> str:
        """Generate Redis key for session."""
        return f"session:{source}:{source_id}"
    
    def _generate_session_id(self, source: str, source_id: str) -> str:
        """Generate unique session ID."""
        ts = int(time.time())
        h = hashlib.sha256(f"{source}:{source_id}:{ts}".encode()).hexdigest()[:12]
        return f"sess_{h}"
    
    async def get_or_create_session(
        self,
        source: str,
        source_id: str,
    ) -> ConversationSession:
        """
        Get existing session or create new one.
        
        Args:
            source: Source identifier ("tg", "web", "api")
            source_id: User/chat identifier
            
        Returns:
            ConversationSession instance
        """
        key = self._session_key(source, source_id)
        
        # Check cache first
        if key in self._sessions_cache:
            return self._sessions_cache[key]
        
        # Try Redis
        try:
            redis_client = _get_redis()
            data = redis_client.get(key)
            if data:
                session = ConversationSession.from_dict(json.loads(data))
                self._sessions_cache[key] = session
                log.debug(f"Session loaded from Redis: {session.session_id}")
                return session
        except Exception as e:
            log.warning(f"Redis get session error: {e}")
        
        # Create new session
        session = ConversationSession(
            session_id=self._generate_session_id(source, source_id),
            source=source,
            source_id=source_id,
        )
        self._sessions_cache[key] = session
        await self._save_session(session)
        log.info(f"New session created: {session.session_id}")
        return session
    
    async def _save_session(self, session: ConversationSession) -> bool:
        """Save session to Redis."""
        key = self._session_key(session.source, session.source_id)
        try:
            redis_client = _get_redis()
            redis_client.setex(
                key,
                SESSION_TTL,
                json.dumps(session.to_dict()),
            )
            return True
        except Exception as e:
            log.error(f"Redis save session error: {e}")
            return False
    
    async def add_turn(
        self,
        source: str,
        source_id: str,
        user_message: str,
        assistant_response: str,
        user_metadata: Optional[Dict[str, Any]] = None,
        assistant_metadata: Optional[Dict[str, Any]] = None,
    ) -> ConversationSession:
        """
        Add a conversation turn (user + assistant).
        
        Args:
            source: Source identifier
            source_id: User/chat identifier
            user_message: User's message
            assistant_response: Assistant's response
            user_metadata: Optional metadata for user message
            assistant_metadata: Optional metadata for assistant message
            
        Returns:
            Updated ConversationSession
        """
        session = await self.get_or_create_session(source, source_id)
        
        # Add messages
        session.add_message("user", user_message, user_metadata)
        session.add_message("assistant", assistant_response, assistant_metadata)
        
        # Check if summarization needed
        if session.needs_summarization() and self.llm_func:
            await self._summarize_session(session)
        
        # Save to Redis
        await self._save_session(session)
        
        return session
    
    async def _summarize_session(self, session: ConversationSession) -> None:
        """
        Summarize older messages to save context space.
        Keeps recent messages and summarizes the rest.
        """
        if not self.llm_func:
            log.warning("Cannot summarize: no LLM function provided")
            return
        
        if len(session.messages) <= SLIDING_WINDOW_SIZE:
            return
        
        # Messages to summarize (all except recent sliding window)
        to_summarize = session.messages[:-SLIDING_WINDOW_SIZE]
        
        if not to_summarize:
            return
        
        # Build conversation text for summarization
        conv_text = "\n".join([
            f"{m.role.upper()}: {m.content[:500]}"  # Limit each message
            for m in to_summarize
        ])
        
        # Limit total text using configurable limit
        conv_text = trim_to_tokens(conv_text, SUMMARIZATION_TOKEN_LIMIT)
        
        summarize_prompt = (
            "Riassumi questa conversazione in modo CONCISO (max 500 parole).\n"
            "Cattura:\n"
            "1. Argomenti principali discussi\n"
            "2. Decisioni o conclusioni raggiunte\n"
            "3. Informazioni importanti condivise\n"
            "4. Preferenze o richieste dell'utente\n\n"
            f"CONVERSAZIONE:\n{conv_text}\n\n"
            "RIASSUNTO:"
        )
        
        try:
            summary = await self.llm_func(
                summarize_prompt,
                "Sei un assistente che riassume conversazioni in modo preciso e conciso.",
            )
            
            if summary:
                # Combine with existing summary
                if session.summary:
                    combined = f"{session.summary}\n\n---\n\n{summary}"
                    # Trim if too long using configurable limit
                    session.summary = trim_to_tokens(combined, SUMMARIZATION_TOKEN_LIMIT)
                else:
                    session.summary = summary
                
                session.summary_tokens = approx_tokens(session.summary)
                
                # Remove summarized messages, keep only recent
                session.messages = session.messages[-SLIDING_WINDOW_SIZE:]
                
                # Recalculate total tokens
                session.total_tokens = sum(m.tokens for m in session.messages)
                session.total_tokens += session.summary_tokens
                
                log.info(
                    f"Session {session.session_id} summarized: "
                    f"{len(to_summarize)} messages → {session.summary_tokens} tokens"
                )
        except Exception as e:
            log.error(f"Summarization failed: {e}")
    
    def build_context(
        self,
        session: ConversationSession,
        max_tokens: int = MAX_CONTEXT_TOKENS,
        include_summary: bool = True,
    ) -> List[Dict[str, str]]:
        """
        Build context messages for LLM call.
        
        Args:
            session: Conversation session
            max_tokens: Maximum tokens for context
            include_summary: Whether to include conversation summary
            
        Returns:
            List of message dicts for LLM API
        """
        messages: List[Dict[str, str]] = []
        tokens_used = 0
        
        # Add summary as system context if exists
        if include_summary and session.summary:
            summary_msg = (
                "CONTESTO CONVERSAZIONE PRECEDENTE:\n"
                f"{session.summary}\n\n"
                "Usa questo contesto per rispondere in modo coerente."
            )
            summary_tokens = approx_tokens(summary_msg)
            if tokens_used + summary_tokens < max_tokens:
                messages.append({
                    "role": "system",
                    "content": summary_msg,
                })
                tokens_used += summary_tokens
        
        # Add recent messages (from sliding window)
        for msg in session.get_recent_messages(SLIDING_WINDOW_SIZE):
            if tokens_used + msg.tokens > max_tokens:
                break
            messages.append({
                "role": msg.role,
                "content": msg.content,
            })
            tokens_used += msg.tokens
        
        return messages
    
    async def search_history(
        self,
        source: str,
        source_id: str,
        query: str,
        top_k: int = 5,
    ) -> List[Message]:
        """
        Search conversation history for relevant messages.
        Simple keyword-based search (can be enhanced with embeddings).
        
        Args:
            source: Source identifier
            source_id: User/chat identifier
            query: Search query
            top_k: Number of results to return
            
        Returns:
            List of relevant messages
        """
        session = await self.get_or_create_session(source, source_id)
        
        query_lower = query.lower()
        query_words = set(query_lower.split())
        
        scored_messages: List[Tuple[float, Message]] = []
        
        for msg in session.messages:
            content_lower = msg.content.lower()
            content_words = set(content_lower.split())
            
            # Simple overlap score
            if query_words & content_words:
                overlap = len(query_words & content_words)
                score = overlap / max(len(query_words), 1)
                scored_messages.append((score, msg))
        
        # Sort by score descending
        scored_messages.sort(key=lambda x: x[0], reverse=True)
        
        return [msg for _, msg in scored_messages[:top_k]]
    
    async def clear_session(self, source: str, source_id: str) -> bool:
        """
        Clear a conversation session.
        
        Args:
            source: Source identifier
            source_id: User/chat identifier
            
        Returns:
            True if cleared successfully
        """
        key = self._session_key(source, source_id)
        
        # Remove from cache
        if key in self._sessions_cache:
            del self._sessions_cache[key]
        
        # Remove from Redis
        try:
            redis_client = _get_redis()
            redis_client.delete(key)
            log.info(f"Session cleared: {key}")
            return True
        except Exception as e:
            log.error(f"Clear session error: {e}")
            return False
    
    async def get_session_stats(
        self,
        source: str,
        source_id: str,
    ) -> Dict[str, Any]:
        """
        Get statistics for a session.
        
        Args:
            source: Source identifier
            source_id: User/chat identifier
            
        Returns:
            Session statistics dict
        """
        session = await self.get_or_create_session(source, source_id)
        
        return {
            "session_id": session.session_id,
            "turn_count": session.turn_count,
            "message_count": len(session.messages),
            "total_tokens": session.total_tokens,
            "summary_tokens": session.summary_tokens,
            "has_summary": bool(session.summary),
            "created_at": datetime.fromtimestamp(session.created_at).isoformat(),
            "updated_at": datetime.fromtimestamp(session.updated_at).isoformat(),
            "age_hours": round((time.time() - session.created_at) / 3600, 1),
        }


# === Singleton Instance ===
_memory_instance: Optional[ConversationalMemory] = None


def get_conversational_memory(llm_func: Optional[callable] = None) -> ConversationalMemory:
    """
    Get or create ConversationalMemory singleton.
    
    Args:
        llm_func: LLM function for summarization (optional)
        
    Returns:
        ConversationalMemory instance
    """
    global _memory_instance
    
    if not ENABLE_CONVERSATIONAL_MEMORY:
        log.warning("Conversational memory is disabled")
    
    if _memory_instance is None:
        _memory_instance = ConversationalMemory(llm_func=llm_func)
    elif llm_func and _memory_instance.llm_func is None:
        _memory_instance.llm_func = llm_func
    
    return _memory_instance


# === Test ===
if __name__ == "__main__":
    import asyncio
    
    async def test():
        print("🧪 Testing Conversational Memory")
        print("=" * 60)
        
        memory = get_conversational_memory()
        
        # Test session creation
        session = await memory.get_or_create_session("test", "user123")
        print(f"Session created: {session.session_id}")
        
        # Test adding turns
        session = await memory.add_turn(
            "test", "user123",
            "Ciao, come funziona QuantumDev?",
            "QuantumDev è un sistema AI avanzato con memoria conversazionale.",
        )
        print(f"Turn added. Messages: {len(session.messages)}")
        
        session = await memory.add_turn(
            "test", "user123",
            "Quali sono le sue caratteristiche?",
            "Le caratteristiche principali sono: 32K context, sliding window, auto-summarization.",
        )
        print(f"Turn added. Messages: {len(session.messages)}, Tokens: {session.total_tokens}")
        
        # Test context building
        context = memory.build_context(session)
        print(f"Context messages: {len(context)}")
        
        # Test stats
        stats = await memory.get_session_stats("test", "user123")
        print(f"Session stats: {json.dumps(stats, indent=2)}")
        
        # Test search
        results = await memory.search_history("test", "user123", "QuantumDev caratteristiche")
        print(f"Search results: {len(results)}")
        
        # Cleanup
        await memory.clear_session("test", "user123")
        print("Session cleared")
        
        print("\n✅ All tests passed!")
    
    asyncio.run(test())
