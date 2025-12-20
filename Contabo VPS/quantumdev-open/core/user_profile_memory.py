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

# Graph traversal configuration
HOP_DISTANCE_WEIGHT_MULTIPLIER = 100  # Weight multiplier for hop distance ranking (direct > 1-hop > 2-hop)

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
    min_relevance: Optional[float] = None,
    use_graph_traversal: bool = True,
    max_graph_hops: int = 2
) -> List[Dict[str, Any]]:
    """
    Query user profile facts with graph-enhanced retrieval.
    
    Workflow:
    1. Extract concepts from query
    2. Perform direct ChromaDB semantic search
    3. If graph traversal enabled:
       - Find related concepts via graph (1-hop, 2-hop, 3-hop)
       - Retrieve docs for related concepts
       - Rank by: direct match > 1-hop > 2-hop > 3-hop
       - Merge and deduplicate results
    4. Add cluster context if available
    
    Args:
        user_id: User identifier
        query_text: Query text for semantic search
        top_k: Number of results to return
        category: Optional category filter
        min_relevance: Minimum relevance threshold (0-1). Defaults to MEMORY_MIN_RELEVANCE env var.
        use_graph_traversal: Enable graph-based expansion
        max_graph_hops: Maximum graph traversal depth (1-3 recommended)
        
    Returns:
        List of matching facts with metadata, ranked by relevance
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
        
        # === STEP 1: Direct ChromaDB Query ===
        fetch_count = top_k * 2 if relevance_threshold > 0 else top_k
        results = col.query(
            query_texts=[query_text],
            n_results=fetch_count,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format and filter results by relevance
        facts = []
        seen_ids = set()
        
        if results and results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                distance = results["distances"][0][i] if results.get("distances") else 1.0
                # Convert distance to similarity (ChromaDB uses cosine distance, so similarity = 1 - distance)
                similarity = 1.0 - distance
                
                # Filter by relevance threshold
                if similarity >= relevance_threshold:
                    fact_id = results["ids"][0][i]
                    fact = {
                        "id": fact_id,
                        "text": results["documents"][0][i] if results.get("documents") else "",
                        "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                        "distance": distance,
                        "similarity": similarity,
                        "match_type": "direct",  # Direct semantic match
                        "hop_distance": 0,  # Direct match has 0 hop distance
                    }
                    facts.append(fact)
                    seen_ids.add(fact_id)
        
        # === STEP 2: Graph Traversal Enhancement ===
        kg = _get_knowledge_graph()
        graph_enriched = False
        concept_clusters = {}
        
        if kg and use_graph_traversal:
            try:
                from core.concept_extractor import extract_concepts
                
                # Extract concepts from query
                query_concepts = extract_concepts(query_text)
                
                # Get concept clusters for labeling
                try:
                    concept_clusters = kg.detect_communities(min_cluster_size=3)
                except Exception as e:
                    log.debug(f"Clustering not available: {e}")
                
                # For each query concept, do multi-hop traversal
                all_related_concepts = {}  # concept -> hop_distance
                
                for concept in query_concepts[:3]:  # Top 3 query concepts
                    if kg.graph.has_node(concept.text):
                        # Multi-hop traversal
                        related_by_hop = kg.find_related_multi_hop(
                            concept.text,
                            max_depth=min(max_graph_hops, 3),  # Cap at 3 hops
                            max_results=15
                        )
                        
                        # Collect all related concepts with their hop distance
                        for hop_dist, related_list in related_by_hop.items():
                            for rel_concept in related_list:
                                # Keep minimum hop distance if concept appears at multiple levels
                                if rel_concept.concept not in all_related_concepts:
                                    all_related_concepts[rel_concept.concept] = hop_dist
                                else:
                                    all_related_concepts[rel_concept.concept] = min(
                                        all_related_concepts[rel_concept.concept],
                                        hop_dist
                                    )
                
                # Query ChromaDB for each related concept
                for related_concept, hop_distance in all_related_concepts.items():
                    try:
                        # Query with related concept as text
                        related_results = col.query(
                            query_texts=[related_concept],
                            n_results=3,  # Limit docs per related concept
                            where=where_filter,
                            include=["documents", "metadatas", "distances"]
                        )
                        
                        if related_results and related_results.get("ids") and related_results["ids"][0]:
                            for i in range(len(related_results["ids"][0])):
                                fact_id = related_results["ids"][0][i]
                                
                                # Skip if already seen
                                if fact_id in seen_ids:
                                    continue
                                
                                distance = related_results["distances"][0][i] if related_results.get("distances") else 1.0
                                similarity = 1.0 - distance
                                
                                # Lower threshold for graph-expanded results
                                if similarity >= (relevance_threshold * 0.8):
                                    fact = {
                                        "id": fact_id,
                                        "text": related_results["documents"][0][i] if related_results.get("documents") else "",
                                        "metadata": related_results["metadatas"][0][i] if related_results.get("metadatas") else {},
                                        "distance": distance,
                                        "similarity": similarity,
                                        "match_type": f"{hop_distance}-hop",  # e.g., "1-hop", "2-hop"
                                        "hop_distance": hop_distance,
                                        "via_concept": related_concept,
                                    }
                                    facts.append(fact)
                                    seen_ids.add(fact_id)
                    
                    except Exception as e:
                        log.debug(f"Failed to query for related concept {related_concept}: {e}")
                
                graph_enriched = True
                log.debug(f"Graph traversal found {len(all_related_concepts)} related concepts")
                
            except Exception as e:
                log.warning(f"Graph traversal failed: {e}")
        
        # === STEP 3: Rank and Sort ===
        # Ranking priority: direct match > 1-hop > 2-hop > 3-hop
        # Within each tier, sort by similarity
        def rank_key(fact):
            hop_distance = fact.get("hop_distance", 0)
            similarity = fact.get("similarity", 0.0)
            # Lower hop distance = higher priority (negative for descending sort)
            # Higher similarity = higher priority
            return (-hop_distance * HOP_DISTANCE_WEIGHT_MULTIPLIER, similarity)
        
        facts.sort(key=rank_key, reverse=True)
        facts = facts[:top_k]
        
        # === STEP 4: Add Cluster Context ===
        if concept_clusters and facts:
            # Get cluster info for enrichment
            cluster_info_cache = {}
            
            for fact in facts:
                # Try to find cluster for concepts mentioned in fact
                fact_text = fact.get("text", "").lower()
                
                # Find which cluster this fact might belong to
                fact_cluster_id = None
                for concept, cluster_id in concept_clusters.items():
                    if concept.lower() in fact_text:
                        fact_cluster_id = cluster_id
                        break
                
                if fact_cluster_id is not None:
                    # Get cluster info (cached)
                    if fact_cluster_id not in cluster_info_cache:
                        cluster_info_cache[fact_cluster_id] = kg.get_cluster_info(
                            fact_cluster_id, concept_clusters
                        )
                    
                    cluster_info = cluster_info_cache[fact_cluster_id]
                    fact["cluster_context"] = f"This relates to {cluster_info['dominant_type']} cluster (size: {cluster_info['size']})"
                    fact["cluster_id"] = fact_cluster_id
        
        # Add metadata about graph enrichment
        if graph_enriched:
            for fact in facts:
                if not fact.get("graph_enriched"):
                    fact["graph_enriched"] = True
        
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
