#!/usr/bin/env python3
"""
core/conversational_web_context.py
===================================

Conversational context manager for web searches that resolves follow-up
queries by tracking last query, entities, and domain.

PROBLEMA 3 FIX: Zero memoria conversazionale in web search
- Classe ConversationalWebManager che traccia last_query, entities, domain
- Metodo resolve_query() che risolve follow-up tipo "E domani?" → "Meteo Roma domani"
- Pattern matching per follow-up: congiunzioni, temporal refs, single-word
- Metodo update_context() per salvare dopo ogni query
"""

from __future__ import annotations

import logging
import re
import time
from typing import Dict, Any, Optional, Set, List
from dataclasses import dataclass, field

# Setup logging
log = logging.getLogger(__name__)

# Follow-up patterns
CONJUNCTION_PATTERNS = [
    r"^\s*e\s+",           # "e domani?"
    r"^\s*e\s+invece",     # "e invece a Milano?"
    r"^\s*ma\s+",          # "ma per Roma?"
    r"^\s*però\s+",        # "però domani?"
    r"^\s*and\s+",         # "and tomorrow?"
]

TEMPORAL_REFS = [
    "domani", "ieri", "oggi",
    "tomorrow", "yesterday", "today",
    "dopodomani", "stanotte",
    "questa settimana", "la prossima settimana",
    "questo mese", "il prossimo mese",
]

# Common interrogative words that indicate a new query (not a follow-up)
NEW_QUERY_INDICATORS = [
    "chi è", "che cos'è", "cos'è", "dove si trova", "quando è",
    "perché", "come funziona", "cosa significa",
    "who is", "what is", "where is", "when is", "why", "how does",
]


@dataclass
class WebContext:
    """Represents the context of a web search conversation.
    
    Attributes
    ----------
    last_query : str
        The most recent query processed.
    entities : Set[str]
        Entities extracted from the last query (e.g., "Roma", "Bitcoin").
    domain : str
        The domain/topic of the last query (e.g., "weather", "price", "sports").
    timestamp : float
        Unix timestamp when context was last updated.
    """
    last_query: str = ""
    entities: Set[str] = field(default_factory=set)
    domain: str = ""
    timestamp: float = 0.0
    
    def is_expired(self, ttl_seconds: float = 300.0) -> bool:
        """Check if context is expired (default: 5 minutes).
        
        Parameters
        ----------
        ttl_seconds : float
            Time-to-live in seconds.
        
        Returns
        -------
        bool
            True if context is expired.
        """
        if not self.timestamp:
            return True
        return (time.time() - self.timestamp) > ttl_seconds
    
    def clear(self) -> None:
        """Clear all context."""
        self.last_query = ""
        self.entities.clear()
        self.domain = ""
        self.timestamp = 0.0


class ConversationalWebManager:
    """Manager for conversational web search context.
    
    Tracks the last query, extracted entities, and domain to resolve
    follow-up queries like "E domani?" → "Meteo Roma domani".
    
    This class implements a session-based context manager that maintains
    conversation state across multiple web search requests.
    
    Examples
    --------
    >>> manager = ConversationalWebManager()
    >>> 
    >>> # First query
    >>> resolved = manager.resolve_query("Meteo Roma", session_id="user123")
    >>> # resolved == "Meteo Roma" (no context yet)
    >>> 
    >>> # Update context after processing
    >>> manager.update_context(
    ...     query="Meteo Roma",
    ...     entities=["Roma"],
    ...     domain="weather",
    ...     session_id="user123"
    ... )
    >>> 
    >>> # Follow-up query
    >>> resolved = manager.resolve_query("E domani?", session_id="user123")
    >>> # resolved == "Meteo Roma domani"
    """
    
    def __init__(self, context_ttl: float = 300.0):
        """Initialize the conversational web manager.
        
        Parameters
        ----------
        context_ttl : float
            Time-to-live for context in seconds (default: 5 minutes).
        """
        self.context_ttl = context_ttl
        
        # Session-based contexts (key: session_id, value: WebContext)
        self._contexts: Dict[str, WebContext] = {}
        
        log.info(f"ConversationalWebManager initialized with TTL={context_ttl}s")
    
    def _is_follow_up(self, query: str) -> bool:
        """Detect if query is a follow-up rather than a new query.
        
        Parameters
        ----------
        query : str
            The query to check.
        
        Returns
        -------
        bool
            True if query appears to be a follow-up.
        """
        if not query:
            return False
        
        query_lower = query.lower().strip()
        
        # Check for new query indicators (definite new queries)
        for indicator in NEW_QUERY_INDICATORS:
            if indicator in query_lower:
                return False
        
        # Check for conjunction patterns
        for pattern in CONJUNCTION_PATTERNS:
            if re.match(pattern, query_lower):
                return True
        
        # Check for single word (might be follow-up)
        words = query_lower.split()
        if len(words) == 1:
            return True
        
        # Check for temporal reference only (2 words max)
        # But not if it's a complete query like "Meteo Roma oggi"
        if len(words) == 2:
            for temp_ref in TEMPORAL_REFS:
                if temp_ref in query_lower and query_lower != temp_ref:
                    # Only if the temporal ref is one of the 2 words
                    if temp_ref in words:
                        return True
        
        return False
    
    def _extract_entities(self, query: str) -> Set[str]:
        """Extract simple entities from query (capitalized words).
        
        This is a simple heuristic extractor. For production, consider
        using NER (Named Entity Recognition) models.
        
        Parameters
        ----------
        query : str
            The query to extract entities from.
        
        Returns
        -------
        Set[str]
            Set of extracted entity strings.
        """
        entities: Set[str] = set()
        
        # Extract capitalized words (likely proper nouns)
        words = query.split()
        for word in words:
            # Remove punctuation
            clean_word = re.sub(r'[?!.,;:]', '', word)
            
            # Check if capitalized and not first word
            if (clean_word and 
                clean_word[0].isupper() and 
                len(clean_word) > 2 and
                not clean_word.isupper()):  # Avoid acronyms like "BTC"
                entities.add(clean_word)
            
            # Also check for well-known entities in lowercase
            clean_lower = clean_word.lower()
            if clean_lower in ["bitcoin", "ethereum", "btc", "eth"]:
                entities.add(clean_word)
        
        return entities
    
    def _detect_domain(self, query: str) -> str:
        """Detect query domain/topic from keywords.
        
        Parameters
        ----------
        query : str
            The query to analyze.
        
        Returns
        -------
        str
            Detected domain (e.g., "weather", "price", "sports", "general").
        """
        query_lower = query.lower()
        
        # Weather keywords
        if any(k in query_lower for k in ["meteo", "tempo", "weather", "temperatura", "pioggia"]):
            return "weather"
        
        # Price keywords
        if any(k in query_lower for k in ["prezzo", "quotazione", "price", "quanto vale", "bitcoin", "btc"]):
            return "price"
        
        # Sports keywords
        if any(k in query_lower for k in ["risultato", "classifica", "partita", "match", "milan", "inter"]):
            return "sports"
        
        # News keywords
        if any(k in query_lower for k in ["notizie", "news", "ultime"]):
            return "news"
        
        return "general"
    
    def resolve_query(self, query: str, session_id: str = "default") -> str:
        """Resolve a query using conversational context if it's a follow-up.
        
        This is the main method for resolving follow-up queries. If the query
        appears to be a follow-up and there's valid context, it will expand
        the query using the previous context.
        
        Parameters
        ----------
        query : str
            The user's query (possibly a follow-up).
        session_id : str
            Session identifier for context isolation.
        
        Returns
        -------
        str
            Resolved query (expanded if follow-up, unchanged if new query).
        
        Examples
        --------
        >>> manager = ConversationalWebManager()
        >>> manager.update_context("Meteo Roma", {"Roma"}, "weather", "s1")
        >>> 
        >>> # Follow-up examples:
        >>> manager.resolve_query("E domani?", "s1")
        "Meteo Roma domani"
        >>> 
        >>> manager.resolve_query("Milano", "s1")  
        "Meteo Milano"  # Inherits domain
        >>> 
        >>> # New query (not a follow-up):
        >>> manager.resolve_query("Prezzo Bitcoin", "s1")
        "Prezzo Bitcoin"  # Unchanged
        """
        if not query or not query.strip():
            return query
        
        # Get context for this session
        context = self._contexts.get(session_id)
        
        # If no context or expired, return original query
        if not context or context.is_expired(self.context_ttl):
            log.debug(f"No valid context for session {session_id}, query unchanged")
            return query
        
        # Check if this is a follow-up
        if not self._is_follow_up(query):
            log.debug(f"Query '{query}' is not a follow-up, unchanged")
            return query
        
        # Try to resolve using context
        query_lower = query.lower().strip()
        
        # Remove conjunction prefix if present
        for pattern in CONJUNCTION_PATTERNS:
            query_lower = re.sub(pattern, "", query_lower)
        
        query_lower = query_lower.strip()
        
        # Build resolved query
        resolved_parts: List[str] = []
        
        # Add domain-specific prefix if available
        if context.domain == "weather" and "meteo" not in query_lower:
            resolved_parts.append("Meteo")
        elif context.domain == "price" and "prezzo" not in query_lower:
            resolved_parts.append("Prezzo")
        elif context.domain == "sports" and "risultato" not in query_lower:
            resolved_parts.append("Risultato")
        
        # If single-word query, check if it's a new entity or a temporal ref
        words = query.split()
        is_single_entity = len(words) == 1 and query[0].isupper()
        
        if is_single_entity:
            # Replace old entity with new one
            resolved_parts.append(query)  # Use capitalized version
        else:
            # Add entities from context (if not already in query)
            for entity in context.entities:
                if entity.lower() not in query_lower:
                    resolved_parts.append(entity)
            
            # Add the actual query
            resolved_parts.append(query_lower)
        
        resolved = " ".join(resolved_parts).strip()
        
        log.info(
            f"Resolved follow-up: '{query}' → '{resolved}' "
            f"(session={session_id}, domain={context.domain})"
        )
        
        return resolved
    
    def update_context(
        self,
        query: str,
        entities: Optional[Set[str]] = None,
        domain: Optional[str] = None,
        session_id: str = "default",
    ) -> None:
        """Update conversational context after processing a query.
        
        Call this method after successfully processing a web search to save
        the context for future follow-up queries.
        
        Parameters
        ----------
        query : str
            The processed query.
        entities : Set[str], optional
            Entities extracted from the query. If None, auto-extract.
        domain : str, optional
            Domain/topic of the query. If None, auto-detect.
        session_id : str
            Session identifier for context isolation.
        
        Examples
        --------
        >>> manager = ConversationalWebManager()
        >>> 
        >>> # Update with explicit entities and domain
        >>> manager.update_context(
        ...     query="Meteo Roma",
        ...     entities={"Roma"},
        ...     domain="weather",
        ...     session_id="user123"
        ... )
        >>> 
        >>> # Update with auto-detection
        >>> manager.update_context(
        ...     query="Prezzo Bitcoin oggi",
        ...     session_id="user123"
        ... )
        """
        if not query:
            return
        
        # Auto-extract entities if not provided
        if entities is None:
            entities = self._extract_entities(query)
        
        # Auto-detect domain if not provided
        if domain is None:
            domain = self._detect_domain(query)
        
        # Create or update context
        if session_id not in self._contexts:
            self._contexts[session_id] = WebContext()
        
        context = self._contexts[session_id]
        context.last_query = query
        context.entities = entities
        context.domain = domain
        context.timestamp = time.time()
        
        log.info(
            f"Updated context for session {session_id}: "
            f"domain={domain}, entities={entities}"
        )
    
    def clear_context(self, session_id: str = "default") -> None:
        """Clear context for a specific session.
        
        Parameters
        ----------
        session_id : str
            Session identifier to clear.
        """
        if session_id in self._contexts:
            self._contexts[session_id].clear()
            log.info(f"Cleared context for session {session_id}")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about managed contexts.
        
        Returns
        -------
        Dict[str, Any]
            Statistics dictionary with context counts and status.
        """
        active_contexts = sum(
            1 for ctx in self._contexts.values()
            if not ctx.is_expired(self.context_ttl)
        )
        
        return {
            "total_sessions": len(self._contexts),
            "active_contexts": active_contexts,
            "context_ttl_seconds": self.context_ttl,
        }


# Singleton instance
_WEB_CONTEXT_MANAGER: Optional[ConversationalWebManager] = None


def get_web_context_manager() -> ConversationalWebManager:
    """Get the singleton web context manager instance.
    
    Returns
    -------
    ConversationalWebManager
        The global web context manager instance.
    
    Examples
    --------
    >>> manager = get_web_context_manager()
    >>> resolved = manager.resolve_query("E domani?", session_id="user123")
    """
    global _WEB_CONTEXT_MANAGER
    
    if _WEB_CONTEXT_MANAGER is None:
        _WEB_CONTEXT_MANAGER = ConversationalWebManager()
        log.info("Created singleton web context manager")
    
    return _WEB_CONTEXT_MANAGER
