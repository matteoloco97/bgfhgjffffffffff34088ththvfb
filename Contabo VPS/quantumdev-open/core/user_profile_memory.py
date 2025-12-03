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

# Environment configuration
USER_PROFILE_COLLECTION = os.getenv("USER_PROFILE_COLLECTION", "user_profile")
USER_PROFILE_ENABLED = os.getenv("USER_PROFILE_ENABLED", "1").strip() in ("1", "true", "yes", "on")
USER_PROFILE_MAX_AGE_DAYS = int(os.getenv("USER_PROFILE_MAX_AGE_DAYS", "365"))

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
        
        log.info(f"Saved user profile fact: {doc_id} (category={category})")
        return doc_id
        
    except Exception as e:
        log.error(f"Failed to save user profile fact: {e}")
        return None


def query_user_profile(
    user_id: str,
    query_text: str,
    top_k: int = 5,
    category: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Query user profile facts.
    
    Args:
        user_id: User identifier
        query_text: Query text for semantic search
        top_k: Number of results to return
        category: Optional category filter
        
    Returns:
        List of matching facts with metadata
    """
    if not USER_PROFILE_ENABLED:
        return []
    
    col = _get_chroma_collection()
    if col is None:
        return []
    
    try:
        # Build where filter
        where_filter = {"user_id": user_id}
        if category:
            where_filter["category"] = category
        
        # Query collection
        results = col.query(
            query_texts=[query_text],
            n_results=top_k,
            where=where_filter,
            include=["documents", "metadatas", "distances"]
        )
        
        # Format results
        facts = []
        if results and results.get("ids") and results["ids"][0]:
            for i in range(len(results["ids"][0])):
                fact = {
                    "id": results["ids"][0][i],
                    "text": results["documents"][0][i] if results.get("documents") else "",
                    "metadata": results["metadatas"][0][i] if results.get("metadatas") else {},
                    "distance": results["distances"][0][i] if results.get("distances") else 1.0,
                }
                facts.append(fact)
        
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
