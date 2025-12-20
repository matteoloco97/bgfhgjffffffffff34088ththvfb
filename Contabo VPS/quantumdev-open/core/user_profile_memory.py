#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/user_profile_memory.py — User Profile Memory System

Manages stable facts and preferences about users (global per user).
- Stable facts: age, city, language, goals, preferences
- "Remember" statement capture and storage
- Category-based organization
"""

import os
import time
import re
import logging
from typing import Dict, List, Any, Optional
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# Lazy import knowledge graph
_kg = None

def _get_knowledge_graph():
    """Lazy import of knowledge graph."""
    global _kg
    if _kg is None:
        try:
            from core.knowledge_graph import get_knowledge_graph
            _kg = get_knowledge_graph()
            if _kg:
                log.info("Knowledge graph integration enabled for user profile memory")
        except Exception as e:
            log.debug(f"Knowledge graph not available: {e}")
            _kg = False
    return _kg if _kg is not False else None

# Environment configuration - OTTIMIZZATO
USER_PROFILE_COLLECTION = os.getenv("USER_PROFILE_COLLECTION", "user_profile")
USER_PROFILE_ENABLED = os.getenv("USER_PROFILE_ENABLED", "1").strip() in ("1", "true", "yes", "on")
USER_PROFILE_MAX_AGE_DAYS = int(os.getenv("USER_PROFILE_MAX_AGE_DAYS", "3650"))  # 10 anni di ritenzione (i fatti personali non scadono facilmente)
MEMORY_MIN_RELEVANCE = float(os.getenv("MEMORY_MIN_RELEVANCE", "0.65"))  # Minimum relevance threshold for memory retrieval

# Default user ID for Matteo (can be extended for multi-user)
DEFAULT_USER_ID = os.getenv("DEFAULT_USER_ID", "matteo")

# Pattern matching for "remember" statements
# Italian patterns
REMEMBER_PATTERNS_IT = [
    r"\bricorda\s+che\s+(.+)",
    r"\bda\s+ora\s+in\s+poi\s+ricord[ao]ti\s+che\s+(.+)",
    r"\bricord[ao]ti\s+(?:di\s+)?(.+)",
    r"\bmemorizz[ao]\s+(?:che\s+)?(.+)",
]

# English patterns  
REMEMBER_PATTERNS_EN = [
    r"\bremember\s+that\s+(.+)",
    r"\bfrom\s+now\s+on,?\s+(?:remember|assume)\s+that\s+(.+)",
    r"\bkeep\s+in\s+mind\s+that\s+(.+)",
    r"\bplease\s+remember\s+(.+)",
]

ALL_REMEMBER_PATTERNS = REMEMBER_PATTERNS_IT + REMEMBER_PATTERNS_EN

# Category keywords for auto-classification
CATEGORY_KEYWORDS = {
    "bio": ["età", "anni", "anno di nascita", "nato", "città", "abito", "vivo", "lingua", "age", "years old", "born", "city", "live", "language"],
    "goal": ["obiettivo", "voglio", "devo", "target", "goal", "aim", "want to", "need to", "should"],
    "preference": ["preferisco", "piace", "tono", "stile", "prefer", "like", "tone", "style"],
    "project": ["progetto", "lavoro", "sto lavorando", "sto facendo", "sto costruendo", "project", "working on", "building"],
}


def _get_chroma_collection():
    """Get or create user profile ChromaDB collection."""
    try:
        from utils.chroma_handler import _col
        return _col(USER_PROFILE_COLLECTION)
    except Exception as e:
        log.error(f"Failed to get user_profile collection: {e}")
        return None


def detect_remember_statement(text: str) -> Optional[str]:
    """
    Detect if text contains a "remember" statement and extract the fact.
    
    Args:
        text: User message text
        
    Returns:
        Extracted fact text or None
    """
    if not text:
        return None
    
    text_lower = text.lower().strip()
    
    for pattern in ALL_REMEMBER_PATTERNS:
        match = re.search(pattern, text_lower, re.IGNORECASE)
        if match:
            fact = match.group(1).strip()
            # Clean up common endings
            fact = re.sub(r'[\.!?]+$', '', fact).strip()
            return fact
    
    return None


def classify_category(fact_text: str) -> str:
    """
    Auto-classify fact into a category based on keywords.
    
    Args:
        fact_text: The fact text to classify
        
    Returns:
        Category name (bio, goal, preference, project, or misc)
    """
    if not fact_text:
        return "misc"
    
    text_lower = fact_text.lower()
    
    # Score each category
    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text_lower)
        if score > 0:
            scores[category] = score
    
    if not scores:
        return "misc"
    
    # Return category with highest score
    return max(scores, key=scores.get)


def save_user_profile_fact(
    user_id: str,
    fact_text: str,
    category: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[str]:
    """
    Save a user profile fact to ChromaDB.
    
    Args:
        user_id: User identifier
        fact_text: The fact content
        category: Fact category (auto-detected if not provided)
        metadata: Additional metadata
        
    Returns:
        Document ID if successful, None otherwise
    """
    if not USER_PROFILE_ENABLED:
        log.debug("User profile memory disabled")
        return None
    
    if not fact_text or not fact_text.strip():
        log.warning("Cannot save empty fact")
        return None
    
    col = _get_chroma_collection()
    if col is None:
        return None
    
    try:
        # Auto-detect category if not provided
        if not category:
            category = classify_category(fact_text)
        
        # Generate unique ID
        timestamp_ms = int(time.time() * 1000)
        doc_id = f"user:{user_id}:{category}:{timestamp_ms}"
        
        # Build metadata
        doc_metadata = {
            "user_id": user_id,
            "category": category,
            "created_at": int(time.time()),
            "updated_at": int(time.time()),
        }
        
        if metadata:
            # Only add ChromaDB-compatible types
            for k, v in metadata.items():
                if isinstance(v, (str, int, float, bool)):
                    doc_metadata[k] = v
        
        # Add to collection
        col.add(
            ids=[doc_id],
            documents=[fact_text],
            metadatas=[doc_metadata]
        )
        
        # Extract concepts and add to knowledge graph
        kg = _get_knowledge_graph()
        if kg:
            try:
                from core.concept_extractor import extract_concepts, extract_relationships
                
                # Extract concepts from fact
                concepts = extract_concepts(fact_text, context=f"user_profile:{category}")
                for concept in concepts[:5]:  # Limit to top 5 concepts
                    kg.add_concept(concept.text, concept.type, {"category": category, "user_id": user_id})
                
                # Extract explicit relationships
                relationships = extract_relationships(fact_text)
                for rel in relationships:
                    kg.add_relationship(rel["source"], rel["target"], rel["relation"], weight=0.9)
                
                # Infer semantic relationships between extracted concepts
                if len(concepts) > 1:
                    for i, concept in enumerate(concepts[:3]):
                        other_concepts = [c.text for j, c in enumerate(concepts) if j != i][:5]
                        inferred = kg.infer_relationships(concept.text, other_concepts)
                        for target, similarity in inferred[:2]:  # Top 2 inferred relationships
                            kg.add_relationship(concept.text, target, "semantic_similarity", similarity)
                
                log.debug(f"Added {len(concepts)} concepts to knowledge graph from fact")
            except Exception as e:
                log.warning(f"Failed to update knowledge graph: {e}")
        
        log.info(f"Saved user profile fact: {doc_id} (category={category})")
        return doc_id
        
    except Exception as e:
        log.error(f"Failed to save user profile fact: {e}")
        return None


def query_user_profile(
    user_id: str,
    query_text: str,
    top_k: int = 5,
    category: Optional[str] = None,
    min_relevance: Optional[float] = None
) -> List[Dict[str, Any]]:
    """
    Query user profile facts with relevance filtering.
    
    Args:
        user_id: User identifier
        query_text: Query text for semantic search
        top_k: Number of results to return
        category: Optional category filter
        min_relevance: Minimum relevance threshold (0-1). Defaults to MEMORY_MIN_RELEVANCE env var.
        
    Returns:
        List of matching facts with metadata, filtered by relevance
    """
    if not USER_PROFILE_ENABLED:
        return []
    
    col = _get_chroma_collection()
    if col is None:
        return []
    
    # Use provided min_relevance or fall back to config
    relevance_threshold = min_relevance if min_relevance is not None else MEMORY_MIN_RELEVANCE
    
    try:
        # Build where filter
        where_filter = {"user_id": user_id}
        if category:
            where_filter["category"] = category
        
        # Query collection - Over-fetch to allow filtering
        fetch_count = top_k * 2 if relevance_threshold > 0 else top_k
        results = col.query(
            query_texts=[query_text],
            n_results=fetch_count,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format and filter results by relevance
        facts = []
        if results and results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                distance = results["distances"][0][i] if results.get("distances") else 1.0
                # Convert distance to similarity (ChromaDB uses cosine distance, so similarity = 1 - distance)
                similarity = 1.0 - distance
                
                # Filter by relevance threshold
                if similarity >= relevance_threshold:
                    fact = {
                        "id": results["ids"][0][i],
                        "text": results["documents"][0][i] if results.get("documents") else "",
                        "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                        "distance": distance,
                        "similarity": similarity,
                    }
                    facts.append(fact)
        
        # Sort by similarity (descending) and limit to top_k
        facts.sort(key=lambda x: x["similarity"], reverse=True)
        facts = facts[:top_k]
        
        # Enrich with knowledge graph context
        kg = _get_knowledge_graph()
        if kg:
            try:
                from core.concept_extractor import extract_concepts
                
                # Extract concepts from query
                query_concepts = extract_concepts(query_text)
                
                # For each concept, find related concepts in graph
                graph_context = []
                for concept in query_concepts[:3]:  # Top 3 concepts
                    related = kg.find_related(concept.text, depth=2, max_results=5)
                    if related:
                        graph_context.extend([
                            f"{concept.text} -> {rel.concept} ({rel.relation_type})"
                            for rel in related[:3]
                        ])
                
                # Add graph context to metadata if available
                if graph_context:
                    for fact in facts:
                        fact["kg_context"] = graph_context[:5]  # Limit to 5 relationships
                        
            except Exception as e:
                log.debug(f"Failed to enrich with knowledge graph: {e}")
        
        return facts
        
    except Exception as e:
        log.error(f"Failed to query user profile: {e}")
        return []


def get_all_user_facts(user_id: str, limit: int = 100) -> List[Dict[str, Any]]:
    """
    Get all facts for a user.
    
    Args:
        user_id: User identifier
        limit: Maximum number of facts to return
        
    Returns:
        List of all user facts
    """
    if not USER_PROFILE_ENABLED:
        return []
    
    col = _get_chroma_collection()
    if col is None:
        return []
    
    try:
        results = col.get(
            where={"user_id": user_id},
            limit=limit,
            include=["documents", "metadatas"]
        )
        
        facts = []
        if results and results.get("ids"):
            for i, doc_id in enumerate(results["ids"]):
                fact = {
                    "id": doc_id,
                    "text": results["documents"][i] if i < len(results.get("documents", [])) else "",
                    "metadata": results["metadatas"][i] if i < len(results.get("metadatas", [])) else {},
                }
                facts.append(fact)
        
        return facts
        
    except Exception as e:
        log.error(f"Failed to get all user facts: {e}")
        return []


def delete_user_fact(fact_id: str) -> bool:
    """
    Delete a specific user fact.
    
    Args:
        fact_id: Fact document ID
        
    Returns:
        True if successful, False otherwise
    """
    col = _get_chroma_collection()
    if col is None:
        return False
    
    try:
        col.delete(ids=[fact_id])
        log.info(f"Deleted user fact: {fact_id}")
        return True
    except Exception as e:
        log.error(f"Failed to delete user fact: {e}")
        return False


def cleanup_old_user_facts(user_id: str, days: int = USER_PROFILE_MAX_AGE_DAYS) -> int:
    """
    Clean up old user facts beyond retention period.
    
    Args:
        user_id: User identifier
        days: Maximum age in days
        
    Returns:
        Number of facts deleted
    """
    col = _get_chroma_collection()
    if col is None:
        return 0
    
    try:
        threshold = int(time.time()) - (days * 86400)
        
        # Get all user facts
        results = col.get(
            where={"user_id": user_id},
            include=["metadatas"]
        )
        
        if not results or not results.get("ids"):
            return 0
        
        # Find old facts
        old_ids = []
        for i, fact_id in enumerate(results["ids"]):
            metadata = results["metadatas"][i] if i < len(results.get("metadatas", [])) else {}
            created_at = metadata.get("created_at", 0)
            if created_at and created_at < threshold:
                old_ids.append(fact_id)
        
        if old_ids:
            col.delete(ids=old_ids)
            log.info(f"Cleaned up {len(old_ids)} old user facts for {user_id}")
        
        return len(old_ids)
        
    except Exception as e:
        log.error(f"Failed to cleanup old user facts: {e}")
        return 0
