#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/semantic_context_analyzer.py — Semantic Context Analysis for QuantumDev Max

Provides semantic analysis of conversational context:
- Topic extraction and clustering
- Context continuity detection
- Semantic relationship analysis between topics
- Topic importance scoring

Author: QuantumDev
Version: 1.0.0
"""

from __future__ import annotations

import os
import time
import math
import logging
from typing import Dict, Any, Optional, List, Tuple, Set
from dataclasses import dataclass, field, asdict
from collections import defaultdict

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
SEMANTIC_ANALYSIS_ENABLED = _env_bool("SEMANTIC_ANALYSIS_ENABLED", True)
TOPIC_SIMILARITY_THRESHOLD = _env_float("TOPIC_SIMILARITY_THRESHOLD", 0.65)
MAX_TOPICS_PER_CONTEXT = _env_int("MAX_TOPICS_PER_CONTEXT", 10)
CONTEXT_CONTINUITY_WINDOW = _env_int("CONTEXT_CONTINUITY_WINDOW", 5)  # Messages to consider for continuity
TOPIC_DECAY_HALF_LIFE_HOURS = _env_float("TOPIC_DECAY_HALF_LIFE_HOURS", 24.0)

# Lazy imports
_embedding_function = None
_np = None


def _get_numpy():
    """Lazy import numpy."""
    global _np
    if _np is None:
        try:
            import numpy as np
            _np = np
        except ImportError:
            log.warning("NumPy not installed, semantic analysis will be limited")
            _np = False
    return _np if _np is not False else None


def _get_embedding_function():
    """Get embedding function from sentence-transformers."""
    global _embedding_function
    if _embedding_function is None:
        try:
            from sentence_transformers import SentenceTransformer
            model_name = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")
            _embedding_function = SentenceTransformer(model_name)
            log.info(f"Loaded embedding model for semantic analysis: {model_name}")
        except Exception as e:
            log.warning(f"Failed to load embedding model: {e}")
            _embedding_function = False
    return _embedding_function if _embedding_function is not False else None


# === Data Classes ===
@dataclass
class Topic:
    """Represents an extracted topic with metadata."""
    text: str
    importance: float = 1.0
    frequency: int = 1
    first_seen: int = field(default_factory=lambda: int(time.time()))
    last_seen: int = field(default_factory=lambda: int(time.time()))
    related_topics: List[str] = field(default_factory=list)
    context_source: str = ""  # e.g., "user", "assistant", "both"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Topic":
        """Create from dictionary."""
        return cls(
            text=data.get("text", ""),
            importance=data.get("importance", 1.0),
            frequency=data.get("frequency", 1),
            first_seen=data.get("first_seen", int(time.time())),
            last_seen=data.get("last_seen", int(time.time())),
            related_topics=data.get("related_topics", []),
            context_source=data.get("context_source", ""),
        )
    
    def decay_importance(self, half_life_hours: float = TOPIC_DECAY_HALF_LIFE_HOURS) -> float:
        """Calculate decayed importance based on time since last seen."""
        now = time.time()
        hours_elapsed = (now - self.last_seen) / 3600
        decay_factor = math.exp(-math.log(2) * hours_elapsed / max(half_life_hours, 0.1))
        return self.importance * decay_factor


@dataclass
class SemanticRelation:
    """Represents a semantic relationship between two items."""
    source: str
    target: str
    similarity: float
    relation_type: str = "semantic_similarity"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return asdict(self)


@dataclass
class ContextAnalysisResult:
    """Result of semantic context analysis."""
    topics: List[Topic]
    relations: List[SemanticRelation]
    continuity_score: float  # 0-1, how related current context is to previous
    dominant_topic: Optional[str]
    topic_shift_detected: bool
    analysis_timestamp: int = field(default_factory=lambda: int(time.time()))
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "topics": [t.to_dict() for t in self.topics],
            "relations": [r.to_dict() for r in self.relations],
            "continuity_score": self.continuity_score,
            "dominant_topic": self.dominant_topic,
            "topic_shift_detected": self.topic_shift_detected,
            "analysis_timestamp": self.analysis_timestamp,
        }


# === Semantic Context Analyzer ===
class SemanticContextAnalyzer:
    """
    Analyzes conversational context for semantic relationships and topic tracking.
    
    Features:
    - Extract topics from messages
    - Cluster related topics
    - Detect context continuity vs topic shifts
    - Score topic importance based on frequency and recency
    - Find semantic relationships between concepts
    """
    
    def __init__(self):
        """Initialize the semantic context analyzer."""
        self._topic_cache: Dict[str, Topic] = {}  # text -> Topic
        self._embedding_cache: Dict[str, Any] = {}  # text -> embedding
        self._last_context_embedding = None
        log.info("SemanticContextAnalyzer initialized")
    
    def _get_embedding(self, text: str) -> Optional[Any]:
        """Get embedding for text, using cache if available."""
        if not text or not text.strip():
            return None
        
        text = text.strip()
        
        # Check cache
        if text in self._embedding_cache:
            return self._embedding_cache[text]
        
        embed_fn = _get_embedding_function()
        if embed_fn is None:
            return None
        
        try:
            embedding = embed_fn.encode([text])[0]
            self._embedding_cache[text] = embedding
            return embedding
        except Exception as e:
            log.warning(f"Failed to get embedding for text: {e}")
            return None
    
    def compute_similarity(self, text1: str, text2: str) -> float:
        """
        Compute semantic similarity between two texts.
        
        Args:
            text1: First text
            text2: Second text
            
        Returns:
            Similarity score (0-1)
        """
        np = _get_numpy()
        if np is None:
            return 0.0
        
        emb1 = self._get_embedding(text1)
        emb2 = self._get_embedding(text2)
        
        if emb1 is None or emb2 is None:
            return 0.0
        
        try:
            similarity = float(np.dot(emb1, emb2) / 
                             (np.linalg.norm(emb1) * np.linalg.norm(emb2)))
            return max(0.0, min(1.0, similarity))
        except Exception as e:
            log.warning(f"Failed to compute similarity: {e}")
            return 0.0
    
    def extract_topics(
        self,
        text: str,
        context_source: str = "user"
    ) -> List[Topic]:
        """
        Extract topics from text using concept extraction.
        
        Args:
            text: Text to extract topics from
            context_source: Source of the text (user, assistant, both)
            
        Returns:
            List of extracted Topic objects
        """
        if not text or not text.strip():
            return []
        
        topics = []
        
        try:
            from core.concept_extractor import extract_concepts
            
            concepts = extract_concepts(text)
            
            for concept in concepts[:MAX_TOPICS_PER_CONTEXT]:
                topic_text = concept.text
                
                # Check if topic already exists in cache
                if topic_text in self._topic_cache:
                    existing = self._topic_cache[topic_text]
                    existing.frequency += 1
                    existing.last_seen = int(time.time())
                    existing.importance = min(existing.importance * 1.1, 2.0)  # Boost importance, cap at 2.0
                    topics.append(existing)
                else:
                    # Create new topic
                    new_topic = Topic(
                        text=topic_text,
                        importance=concept.confidence,
                        frequency=1,
                        context_source=context_source,
                    )
                    self._topic_cache[topic_text] = new_topic
                    topics.append(new_topic)
            
        except Exception as e:
            log.warning(f"Topic extraction failed: {e}")
            # Fallback: extract capitalized words as topics
            topics = self._extract_topics_fallback(text, context_source)
        
        return topics
    
    def _extract_topics_fallback(
        self,
        text: str,
        context_source: str = "user"
    ) -> List[Topic]:
        """Fallback topic extraction without concept_extractor."""
        topics = []
        words = text.split()
        
        # Extract capitalized words as potential topics
        for word in words:
            word = word.strip('.,!?;:()[]{}\"\'')
            if len(word) >= 3 and word[0].isupper():
                if word not in self._topic_cache:
                    topic = Topic(
                        text=word,
                        importance=0.5,
                        frequency=1,
                        context_source=context_source,
                    )
                    self._topic_cache[word] = topic
                    topics.append(topic)
                else:
                    existing = self._topic_cache[word]
                    existing.frequency += 1
                    existing.last_seen = int(time.time())
                    topics.append(existing)
        
        return topics[:MAX_TOPICS_PER_CONTEXT]
    
    def find_semantic_relations(
        self,
        topics: List[Topic],
        threshold: float = TOPIC_SIMILARITY_THRESHOLD
    ) -> List[SemanticRelation]:
        """
        Find semantic relationships between topics.
        
        Args:
            topics: List of topics to analyze
            threshold: Minimum similarity threshold
            
        Returns:
            List of SemanticRelation objects
        """
        relations = []
        topic_texts = [t.text for t in topics]
        
        # Compare each pair of topics
        for i, topic1 in enumerate(topic_texts):
            for j, topic2 in enumerate(topic_texts):
                if i >= j:  # Skip self-comparisons and duplicates
                    continue
                
                similarity = self.compute_similarity(topic1, topic2)
                
                if similarity >= threshold:
                    relations.append(SemanticRelation(
                        source=topic1,
                        target=topic2,
                        similarity=similarity,
                        relation_type="semantic_similarity"
                    ))
                    
                    # Update related_topics in cache
                    if topic1 in self._topic_cache:
                        if topic2 not in self._topic_cache[topic1].related_topics:
                            self._topic_cache[topic1].related_topics.append(topic2)
                    if topic2 in self._topic_cache:
                        if topic1 not in self._topic_cache[topic2].related_topics:
                            self._topic_cache[topic2].related_topics.append(topic1)
        
        # Sort by similarity (descending)
        relations.sort(key=lambda r: r.similarity, reverse=True)
        return relations
    
    def analyze_context_continuity(
        self,
        current_text: str,
        previous_texts: List[str]
    ) -> Tuple[float, bool]:
        """
        Analyze if current context is continuous with previous context.
        
        Args:
            current_text: Current message text
            previous_texts: List of previous message texts
            
        Returns:
            Tuple of (continuity_score, topic_shift_detected)
        """
        if not previous_texts:
            return 1.0, False  # No previous context, assume continuous
        
        np = _get_numpy()
        if np is None:
            return 0.5, False  # Can't compute, assume moderate continuity
        
        current_emb = self._get_embedding(current_text)
        if current_emb is None:
            return 0.5, False
        
        # Compute similarity with recent messages (weighted by recency)
        similarities = []
        weights = []
        
        for i, prev_text in enumerate(reversed(previous_texts[-CONTEXT_CONTINUITY_WINDOW:])):
            prev_emb = self._get_embedding(prev_text)
            if prev_emb is not None:
                try:
                    sim = float(np.dot(current_emb, prev_emb) / 
                               (np.linalg.norm(current_emb) * np.linalg.norm(prev_emb)))
                    sim = max(0.0, min(1.0, sim))
                    similarities.append(sim)
                    # More recent messages have higher weight
                    weights.append(1.0 / (i + 1))
                except Exception:
                    pass
        
        if not similarities:
            return 0.5, False
        
        # Weighted average similarity
        total_weight = sum(weights)
        weighted_sum = sum(s * w for s, w in zip(similarities, weights))
        continuity_score = weighted_sum / total_weight if total_weight > 0 else 0.5
        
        # Topic shift detected if continuity is below threshold
        topic_shift = continuity_score < TOPIC_SIMILARITY_THRESHOLD
        
        return continuity_score, topic_shift
    
    def analyze(
        self,
        current_text: str,
        previous_texts: Optional[List[str]] = None,
        context_source: str = "user"
    ) -> ContextAnalysisResult:
        """
        Perform full semantic analysis of context.
        
        Args:
            current_text: Current message to analyze
            previous_texts: Optional list of previous messages
            context_source: Source of the current text
            
        Returns:
            ContextAnalysisResult with analysis details
        """
        if not SEMANTIC_ANALYSIS_ENABLED:
            return ContextAnalysisResult(
                topics=[],
                relations=[],
                continuity_score=1.0,
                dominant_topic=None,
                topic_shift_detected=False,
            )
        
        # Extract topics
        topics = self.extract_topics(current_text, context_source)
        
        # Find semantic relations
        relations = self.find_semantic_relations(topics)
        
        # Analyze context continuity
        previous_texts = previous_texts or []
        continuity_score, topic_shift = self.analyze_context_continuity(
            current_text, previous_texts
        )
        
        # Determine dominant topic (highest importance with decay)
        dominant_topic = None
        if topics:
            # Score topics by decayed importance and frequency
            scored_topics = [
                (t, t.decay_importance() * math.log1p(t.frequency))
                for t in topics
            ]
            scored_topics.sort(key=lambda x: x[1], reverse=True)
            dominant_topic = scored_topics[0][0].text if scored_topics else None
        
        return ContextAnalysisResult(
            topics=topics,
            relations=relations,
            continuity_score=continuity_score,
            dominant_topic=dominant_topic,
            topic_shift_detected=topic_shift,
        )
    
    def get_topic_importance_scores(self) -> Dict[str, float]:
        """
        Get current importance scores for all tracked topics.
        
        Returns:
            Dict mapping topic text to decayed importance score
        """
        scores = {}
        for text, topic in self._topic_cache.items():
            scores[text] = topic.decay_importance()
        return scores
    
    def get_related_topics(
        self,
        topic_text: str,
        max_results: int = 5
    ) -> List[Tuple[str, float]]:
        """
        Get topics related to a given topic.
        
        Args:
            topic_text: Topic to find relations for
            max_results: Maximum number of related topics
            
        Returns:
            List of (topic_text, similarity) tuples
        """
        if topic_text not in self._topic_cache:
            return []
        
        related = []
        topic = self._topic_cache[topic_text]
        
        # Get cached related topics with similarity scores
        for related_text in topic.related_topics:
            if related_text in self._topic_cache:
                similarity = self.compute_similarity(topic_text, related_text)
                related.append((related_text, similarity))
        
        # Sort by similarity and return top results
        related.sort(key=lambda x: x[1], reverse=True)
        return related[:max_results]
    
    def cluster_topics(
        self,
        topics: Optional[List[Topic]] = None,
        threshold: float = TOPIC_SIMILARITY_THRESHOLD
    ) -> Dict[int, List[str]]:
        """
        Cluster topics based on semantic similarity.
        
        Args:
            topics: Topics to cluster (uses all cached if None)
            threshold: Similarity threshold for clustering
            
        Returns:
            Dict mapping cluster_id to list of topic texts
        """
        if topics is None:
            topics = list(self._topic_cache.values())
        
        if not topics:
            return {}
        
        # Simple agglomerative clustering based on similarity
        topic_texts = [t.text for t in topics]
        clusters: Dict[int, Set[str]] = {}
        cluster_id = 0
        assigned = set()
        
        for i, topic1 in enumerate(topic_texts):
            if topic1 in assigned:
                continue
            
            # Start new cluster
            current_cluster = {topic1}
            assigned.add(topic1)
            
            # Find all similar topics
            for j, topic2 in enumerate(topic_texts):
                if i == j or topic2 in assigned:
                    continue
                
                similarity = self.compute_similarity(topic1, topic2)
                if similarity >= threshold:
                    current_cluster.add(topic2)
                    assigned.add(topic2)
            
            clusters[cluster_id] = current_cluster
            cluster_id += 1
        
        # Convert sets to lists
        return {k: list(v) for k, v in clusters.items()}
    
    def clear_cache(self):
        """Clear all cached data."""
        self._topic_cache.clear()
        self._embedding_cache.clear()
        self._last_context_embedding = None
        log.info("SemanticContextAnalyzer cache cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """Get analyzer statistics."""
        return {
            "cached_topics": len(self._topic_cache),
            "cached_embeddings": len(self._embedding_cache),
            "enabled": SEMANTIC_ANALYSIS_ENABLED,
        }


# === Singleton Instance ===
_analyzer_instance: Optional[SemanticContextAnalyzer] = None


def get_semantic_analyzer() -> SemanticContextAnalyzer:
    """
    Get or create SemanticContextAnalyzer singleton.
    
    Returns:
        SemanticContextAnalyzer instance
    """
    global _analyzer_instance
    
    if _analyzer_instance is None:
        _analyzer_instance = SemanticContextAnalyzer()
    
    return _analyzer_instance


# === Test ===
if __name__ == "__main__":
    print("🧪 Testing Semantic Context Analyzer")
    print("=" * 60)
    
    analyzer = get_semantic_analyzer()
    
    # Test topic extraction
    text1 = "I'm working on a Python project using FastAPI and ChromaDB."
    topics1 = analyzer.extract_topics(text1)
    print(f"\n📊 Topics from text 1:")
    for t in topics1:
        print(f"  - {t.text} (importance: {t.importance:.2f})")
    
    # Test with second message
    text2 = "FastAPI is great for building REST APIs with Python."
    topics2 = analyzer.extract_topics(text2)
    print(f"\n📊 Topics from text 2:")
    for t in topics2:
        print(f"  - {t.text} (importance: {t.importance:.2f}, freq: {t.frequency})")
    
    # Test semantic relations
    all_topics = topics1 + topics2
    relations = analyzer.find_semantic_relations(all_topics)
    print(f"\n🔗 Semantic relations:")
    for r in relations[:5]:
        print(f"  - {r.source} <-> {r.target} (sim: {r.similarity:.2f})")
    
    # Test context continuity
    text3 = "Let's talk about machine learning and neural networks."
    continuity, shift = analyzer.analyze_context_continuity(text3, [text1, text2])
    print(f"\n📈 Context continuity for text3:")
    print(f"  - Continuity score: {continuity:.2f}")
    print(f"  - Topic shift detected: {shift}")
    
    # Full analysis
    result = analyzer.analyze(text1, previous_texts=[])
    print(f"\n🎯 Full analysis result:")
    print(f"  - Topics: {len(result.topics)}")
    print(f"  - Relations: {len(result.relations)}")
    print(f"  - Dominant topic: {result.dominant_topic}")
    print(f"  - Continuity: {result.continuity_score:.2f}")
    
    # Topic clustering
    clusters = analyzer.cluster_topics()
    print(f"\n🏷️ Topic clusters: {len(clusters)}")
    for cid, members in clusters.items():
        print(f"  Cluster {cid}: {', '.join(members)}")
    
    # Stats
    stats = analyzer.get_stats()
    print(f"\n📈 Stats: {stats}")
    
    print("\n✅ Test complete!")
