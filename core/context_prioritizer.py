#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/context_prioritizer.py — Intelligent Context Prioritization for QuantumDev Max

Provides intelligent prioritization of context for LLM calls:
- Token budget-aware prioritization
- Relevance scoring system
- Recency vs importance balancing
- Context compression utilities

Author: QuantumDev
Version: 1.0.0
"""

from __future__ import annotations

import os
import time
import math
import logging
from typing import Dict, Any, Optional, List, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === ENV Configuration ===
def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        return float(raw)
    except ValueError:
        return default


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        return int(raw)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


# Configuration
CONTEXT_PRIORITIZATION_ENABLED = _env_bool("CONTEXT_PRIORITIZATION_ENABLED", True)
DEFAULT_TOKEN_BUDGET = _env_int("DEFAULT_CONTEXT_TOKEN_BUDGET", 8000)
RECENCY_WEIGHT = _env_float("CONTEXT_RECENCY_WEIGHT", 0.3)
RELEVANCE_WEIGHT = _env_float("CONTEXT_RELEVANCE_WEIGHT", 0.5)
IMPORTANCE_WEIGHT = _env_float("CONTEXT_IMPORTANCE_WEIGHT", 0.2)
RECENCY_HALF_LIFE_HOURS = _env_float("CONTEXT_RECENCY_HALF_LIFE_HOURS", 24.0)

# Compression settings
COMPRESSION_RATIO_TARGET = _env_float("CONTEXT_COMPRESSION_RATIO", 0.5)  # Target 50% of original
MIN_CONTEXT_ITEM_TOKENS = _env_int("MIN_CONTEXT_ITEM_TOKENS", 10)

# Lazy imports
_np = None
_semantic_analyzer = None


def _get_numpy():
    """Lazy import numpy."""
    global _np
    if _np is None:
        try:
            import numpy as np
            _np = np
        except ImportError:
            log.warning("NumPy not installed")
            _np = False
    return _np if _np is not False else None


def _get_semantic_analyzer():
    """Lazy import semantic analyzer to avoid circular imports."""
    global _semantic_analyzer
    if _semantic_analyzer is None:
        try:
            from core.semantic_context_analyzer import get_semantic_analyzer
            _semantic_analyzer = get_semantic_analyzer()
            log.debug("Semantic analyzer loaded for context prioritizer")
        except ImportError as e:
            log.debug(f"Semantic analyzer not available: {e}")
            _semantic_analyzer = False
    return _semantic_analyzer if _semantic_analyzer is not False else None


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


# === Enums ===
class ContextType(Enum):
    """Types of context items."""
    SYSTEM = "system"
    CONVERSATION = "conversation"
    USER_PROFILE = "user_profile"
    KNOWLEDGE_GRAPH = "knowledge_graph"
    EPISODIC = "episodic"
    SUMMARY = "summary"
    TOOL_RESULT = "tool_result"


class PriorityLevel(Enum):
    """Priority levels for context items."""
    CRITICAL = 5  # Must include (system prompts, current query)
    HIGH = 4      # Very important (recent context, user preferences)
    MEDIUM = 3    # Important (related context)
    LOW = 2       # Nice to have (background info)
    MINIMAL = 1   # Include only if space permits


# === Data Classes ===
@dataclass
class ContextItem:
    """Represents a single context item with metadata for prioritization."""
    content: str
    context_type: ContextType
    priority: PriorityLevel = PriorityLevel.MEDIUM
    relevance_score: float = 0.5  # 0-1, how relevant to current query
    recency_timestamp: int = field(default_factory=lambda: int(time.time()))
    importance_score: float = 0.5  # 0-1, intrinsic importance
    source: str = ""  # Source identifier
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    @property
    def tokens(self) -> int:
        """Get approximate token count."""
        return approx_tokens(self.content)
    
    def compute_priority_score(
        self,
        recency_weight: float = RECENCY_WEIGHT,
        relevance_weight: float = RELEVANCE_WEIGHT,
        importance_weight: float = IMPORTANCE_WEIGHT,
        recency_half_life_hours: float = RECENCY_HALF_LIFE_HOURS,
    ) -> float:
        """
        Compute overall priority score for this item.
        
        Returns:
            Priority score (higher = more important)
        """
        # Base priority from level
        base_priority = self.priority.value / 5.0  # Normalize to 0-1
        
        # Recency score with exponential decay
        now = time.time()
        hours_elapsed = (now - self.recency_timestamp) / 3600
        recency_score = math.exp(-math.log(2) * hours_elapsed / max(recency_half_life_hours, 0.1))
        
        # Combine scores
        combined = (
            base_priority * 0.3 +  # Base priority contributes 30%
            recency_score * recency_weight +
            self.relevance_score * relevance_weight +
            self.importance_score * importance_weight
        )
        
        return min(1.0, max(0.0, combined))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "content": self.content,
            "context_type": self.context_type.value,
            "priority": self.priority.value,
            "relevance_score": self.relevance_score,
            "recency_timestamp": self.recency_timestamp,
            "importance_score": self.importance_score,
            "source": self.source,
            "metadata": self.metadata,
            "tokens": self.tokens,
        }


@dataclass
class PrioritizationResult:
    """Result of context prioritization."""
    selected_items: List[ContextItem]
    excluded_items: List[ContextItem]
    total_tokens: int
    budget_used: int
    budget_remaining: int
    compression_applied: bool
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "selected_count": len(self.selected_items),
            "excluded_count": len(self.excluded_items),
            "total_tokens": self.total_tokens,
            "budget_used": self.budget_used,
            "budget_remaining": self.budget_remaining,
            "compression_applied": self.compression_applied,
        }


# === Context Prioritizer ===
class ContextPrioritizer:
    """
    Intelligently prioritizes context items within token budget.
    
    Features:
    - Score items based on relevance, recency, and importance
    - Select items within token budget
    - Compress context when necessary
    - Handle different context types with appropriate strategies
    """
    
    def __init__(
        self,
        token_budget: int = DEFAULT_TOKEN_BUDGET,
        recency_weight: float = RECENCY_WEIGHT,
        relevance_weight: float = RELEVANCE_WEIGHT,
        importance_weight: float = IMPORTANCE_WEIGHT,
    ):
        """
        Initialize the context prioritizer.
        
        Args:
            token_budget: Maximum tokens for context
            recency_weight: Weight for recency in scoring
            relevance_weight: Weight for relevance in scoring
            importance_weight: Weight for importance in scoring
        """
        self.token_budget = token_budget
        self.recency_weight = recency_weight
        self.relevance_weight = relevance_weight
        self.importance_weight = importance_weight
        log.info(f"ContextPrioritizer initialized with budget={token_budget}")
    
    def prioritize(
        self,
        items: List[ContextItem],
        current_query: Optional[str] = None,
        budget_override: Optional[int] = None,
    ) -> PrioritizationResult:
        """
        Prioritize context items within token budget.
        
        Args:
            items: List of context items to prioritize
            current_query: Optional current query for relevance scoring
            budget_override: Override the default token budget
            
        Returns:
            PrioritizationResult with selected and excluded items
        """
        if not CONTEXT_PRIORITIZATION_ENABLED:
            # Return all items if prioritization disabled
            total_tokens = sum(item.tokens for item in items)
            return PrioritizationResult(
                selected_items=items,
                excluded_items=[],
                total_tokens=total_tokens,
                budget_used=total_tokens,
                budget_remaining=0,
                compression_applied=False,
            )
        
        budget = budget_override or self.token_budget
        
        # Update relevance scores if query provided
        if current_query:
            self._update_relevance_scores(items, current_query)
        
        # Score and sort items
        scored_items = [
            (item, item.compute_priority_score(
                self.recency_weight,
                self.relevance_weight,
                self.importance_weight,
            ))
            for item in items
        ]
        scored_items.sort(key=lambda x: x[1], reverse=True)
        
        # Select items within budget
        selected = []
        excluded = []
        tokens_used = 0
        
        # First pass: include all CRITICAL items
        for item, score in scored_items:
            if item.priority == PriorityLevel.CRITICAL:
                if tokens_used + item.tokens <= budget:
                    selected.append(item)
                    tokens_used += item.tokens
                else:
                    # Try to compress critical items
                    compressed = self._compress_item(item, budget - tokens_used)
                    if compressed and compressed.tokens > MIN_CONTEXT_ITEM_TOKENS:
                        selected.append(compressed)
                        tokens_used += compressed.tokens
                    else:
                        excluded.append(item)
        
        # Second pass: add remaining items by priority score
        for item, score in scored_items:
            if item.priority == PriorityLevel.CRITICAL:
                continue  # Already processed
            
            if tokens_used + item.tokens <= budget:
                selected.append(item)
                tokens_used += item.tokens
            elif budget - tokens_used >= MIN_CONTEXT_ITEM_TOKENS:
                # Try to fit a compressed version
                compressed = self._compress_item(item, budget - tokens_used)
                if compressed and compressed.tokens >= MIN_CONTEXT_ITEM_TOKENS:
                    selected.append(compressed)
                    tokens_used += compressed.tokens
                else:
                    excluded.append(item)
            else:
                excluded.append(item)
        
        # Check if compression was applied
        compression_applied = any(
            hasattr(item, '_compressed') and item._compressed
            for item in selected
        )
        
        total_tokens = sum(item.tokens for item in items)
        
        return PrioritizationResult(
            selected_items=selected,
            excluded_items=excluded,
            total_tokens=total_tokens,
            budget_used=tokens_used,
            budget_remaining=budget - tokens_used,
            compression_applied=compression_applied,
        )
    
    def _update_relevance_scores(
        self,
        items: List[ContextItem],
        query: str
    ) -> None:
        """Update relevance scores based on current query."""
        # Use lazy-loaded semantic analyzer
        analyzer = _get_semantic_analyzer()
        if analyzer is not None:
            try:
                for item in items:
                    similarity = analyzer.compute_similarity(query, item.content)
                    item.relevance_score = similarity
                return
            except Exception as e:
                log.debug(f"Could not compute semantic relevance: {e}")
        
        # Fallback: simple keyword overlap
        query_words = set(query.lower().split())
        for item in items:
            content_words = set(item.content.lower().split())
            overlap = len(query_words & content_words)
            item.relevance_score = min(1.0, overlap / max(len(query_words), 1))
    
    def _compress_item(
        self,
        item: ContextItem,
        max_tokens: int
    ) -> Optional[ContextItem]:
        """
        Compress a context item to fit within token limit.
        
        Args:
            item: Item to compress
            max_tokens: Maximum tokens for compressed item
            
        Returns:
            Compressed ContextItem or None if too small
        """
        if item.tokens <= max_tokens:
            return item
        
        if max_tokens < MIN_CONTEXT_ITEM_TOKENS:
            return None
        
        # Simple compression: truncate content
        compressed_content = trim_to_tokens(item.content, max_tokens)
        
        # Add truncation indicator
        if len(compressed_content) < len(item.content):
            # Reserve some space for truncation indicator
            compressed_content = trim_to_tokens(item.content, max_tokens - 3)
            compressed_content = compressed_content.rstrip() + "..."
        
        compressed = ContextItem(
            content=compressed_content,
            context_type=item.context_type,
            priority=item.priority,
            relevance_score=item.relevance_score,
            recency_timestamp=item.recency_timestamp,
            importance_score=item.importance_score * 0.9,  # Slight penalty for compression
            source=item.source,
            metadata={**item.metadata, "compressed": True, "original_tokens": item.tokens},
        )
        compressed._compressed = True  # type: ignore
        
        return compressed
    
    def build_context_string(
        self,
        result: PrioritizationResult,
        separator: str = "\n\n"
    ) -> str:
        """
        Build a combined context string from prioritized items.
        
        Args:
            result: PrioritizationResult from prioritize()
            separator: Separator between context items
            
        Returns:
            Combined context string
        """
        # Group by context type for organized output
        by_type: Dict[ContextType, List[ContextItem]] = {}
        for item in result.selected_items:
            if item.context_type not in by_type:
                by_type[item.context_type] = []
            by_type[item.context_type].append(item)
        
        parts = []
        
        # Order by context type importance
        type_order = [
            ContextType.SYSTEM,
            ContextType.SUMMARY,
            ContextType.USER_PROFILE,
            ContextType.KNOWLEDGE_GRAPH,
            ContextType.CONVERSATION,
            ContextType.EPISODIC,
            ContextType.TOOL_RESULT,
        ]
        
        for ctx_type in type_order:
            if ctx_type in by_type:
                for item in by_type[ctx_type]:
                    parts.append(item.content)
        
        return separator.join(parts)


# === Convenience Functions ===
def prioritize_context(
    items: List[ContextItem],
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    current_query: Optional[str] = None,
) -> PrioritizationResult:
    """
    Convenience function to prioritize context items.
    
    Args:
        items: List of context items
        token_budget: Token budget
        current_query: Optional current query
        
    Returns:
        PrioritizationResult
    """
    prioritizer = ContextPrioritizer(token_budget=token_budget)
    return prioritizer.prioritize(items, current_query)


def create_context_item(
    content: str,
    context_type: str = "conversation",
    priority: str = "medium",
    relevance: float = 0.5,
    importance: float = 0.5,
    timestamp: Optional[int] = None,
    source: str = "",
) -> ContextItem:
    """
    Convenience function to create a context item.
    
    Args:
        content: Content text
        context_type: Type of context (system, conversation, etc.)
        priority: Priority level (critical, high, medium, low, minimal)
        relevance: Relevance score (0-1)
        importance: Importance score (0-1)
        timestamp: Recency timestamp
        source: Source identifier
        
    Returns:
        ContextItem
    """
    # Map string to enum
    type_map = {
        "system": ContextType.SYSTEM,
        "conversation": ContextType.CONVERSATION,
        "user_profile": ContextType.USER_PROFILE,
        "knowledge_graph": ContextType.KNOWLEDGE_GRAPH,
        "episodic": ContextType.EPISODIC,
        "summary": ContextType.SUMMARY,
        "tool_result": ContextType.TOOL_RESULT,
    }
    
    priority_map = {
        "critical": PriorityLevel.CRITICAL,
        "high": PriorityLevel.HIGH,
        "medium": PriorityLevel.MEDIUM,
        "low": PriorityLevel.LOW,
        "minimal": PriorityLevel.MINIMAL,
    }
    
    return ContextItem(
        content=content,
        context_type=type_map.get(context_type.lower(), ContextType.CONVERSATION),
        priority=priority_map.get(priority.lower(), PriorityLevel.MEDIUM),
        relevance_score=relevance,
        importance_score=importance,
        recency_timestamp=timestamp or int(time.time()),
        source=source,
    )


def allocate_budget(
    total_budget: int,
    allocations: Dict[str, float],
) -> Dict[str, int]:
    """
    Allocate token budget across different context types.
    
    Args:
        total_budget: Total token budget
        allocations: Dict mapping type name to percentage (0-1)
        
    Returns:
        Dict mapping type name to allocated tokens
    """
    result = {}
    total_pct = sum(allocations.values())
    
    for name, pct in allocations.items():
        normalized_pct = pct / total_pct if total_pct > 0 else 0
        result[name] = int(total_budget * normalized_pct)
    
    return result


# === Singleton Instance ===
_prioritizer_instance: Optional[ContextPrioritizer] = None


def get_context_prioritizer(
    token_budget: Optional[int] = None
) -> ContextPrioritizer:
    """
    Get or create ContextPrioritizer singleton.
    
    Args:
        token_budget: Optional token budget override
        
    Returns:
        ContextPrioritizer instance
    """
    global _prioritizer_instance
    
    if _prioritizer_instance is None:
        _prioritizer_instance = ContextPrioritizer(
            token_budget=token_budget or DEFAULT_TOKEN_BUDGET
        )
    elif token_budget is not None:
        _prioritizer_instance.token_budget = token_budget
    
    return _prioritizer_instance


# === Test ===
if __name__ == "__main__":
    print("🧪 Testing Context Prioritizer")
    print("=" * 60)
    
    # Create test items
    items = [
        create_context_item(
            "You are an AI assistant helping with Python development.",
            context_type="system",
            priority="critical",
            importance=1.0,
        ),
        create_context_item(
            "User prefers concise answers.",
            context_type="user_profile",
            priority="high",
            importance=0.8,
        ),
        create_context_item(
            "Previously discussed FastAPI and REST APIs.",
            context_type="episodic",
            priority="medium",
            importance=0.6,
        ),
        create_context_item(
            "User asked about database optimization yesterday.",
            context_type="conversation",
            priority="low",
            importance=0.4,
            timestamp=int(time.time()) - 86400,  # 1 day ago
        ),
        create_context_item(
            "Background information about Python virtual environments.",
            context_type="conversation",
            priority="minimal",
            importance=0.3,
        ),
    ]
    
    print("\n📥 Input items:")
    for item in items:
        print(f"  - [{item.context_type.value}] {item.content[:50]}... ({item.tokens} tokens)")
    
    # Prioritize with budget
    prioritizer = get_context_prioritizer(token_budget=100)
    result = prioritizer.prioritize(items, current_query="How do I use FastAPI?")
    
    print(f"\n📊 Prioritization result:")
    print(f"  Budget: {prioritizer.token_budget}")
    print(f"  Used: {result.budget_used}")
    print(f"  Remaining: {result.budget_remaining}")
    print(f"  Compression: {result.compression_applied}")
    
    print(f"\n✅ Selected items ({len(result.selected_items)}):")
    for item in result.selected_items:
        score = item.compute_priority_score()
        print(f"  - [{item.priority.name}] {item.content[:40]}... (score: {score:.2f})")
    
    print(f"\n❌ Excluded items ({len(result.excluded_items)}):")
    for item in result.excluded_items:
        print(f"  - [{item.priority.name}] {item.content[:40]}...")
    
    # Build context string
    context_str = prioritizer.build_context_string(result)
    print(f"\n📝 Built context ({approx_tokens(context_str)} tokens):")
    print(context_str[:200] + "..." if len(context_str) > 200 else context_str)
    
    # Budget allocation
    print("\n💰 Budget allocation example:")
    alloc = allocate_budget(1000, {
        "system": 0.1,
        "user_profile": 0.2,
        "conversation": 0.5,
        "episodic": 0.2,
    })
    for name, tokens in alloc.items():
        print(f"  - {name}: {tokens} tokens")
    
    print("\n✅ Test complete!")
