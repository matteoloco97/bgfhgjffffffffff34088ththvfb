#!/usr/bin/env python3
"""
core/multi_search_aggregator.py
================================
Multi-engine search aggregation con deduplicazione intelligente.
"""

import asyncio
import os
from typing import List, Dict, Any
from urllib.parse import urlparse
import logging

log = logging.getLogger(__name__)

# Configurazione da env
BRAVE_API_KEY = os.getenv("BRAVE_SEARCH_API_KEY", "")
BRAVE_ENABLED = os.getenv("BRAVE_SEARCH_ENABLED", "1") == "1"
BRAVE_COUNT = int(os.getenv("BRAVE_SEARCH_COUNT", "10"))
DEDUP_THRESHOLD = float(os.getenv("MULTI_ENGINE_DEDUP_THRESHOLD", "0.85"))

async def search_brave(query: str, count: int = 10) -> List[Dict[str, Any]]:
    """Search usando Brave Search API."""
    if not BRAVE_API_KEY or not BRAVE_ENABLED:
        return []
    
    try:
        from brave import Brave
        brave = Brave(api_key=BRAVE_API_KEY)
        
        # Async search
        results = await asyncio.to_thread(
            brave.search,
            q=query,
            count=count
        )
        
        # Format results
        formatted = []
        for r in results.web_results:
            formatted.append({
                "url": r.url,
                "title": r.title,
                "snippet": r.description,
                "source": "brave"
            })
        
        log.info(f"Brave Search: {len(formatted)} results for '{query}'")
        return formatted
    
    except Exception as e:
        log.warning(f"Brave Search failed: {e}")
        return []

def fuzzy_url_match(url1: str, url2: str) -> float:
    """Similarity score tra due URL (0-1)."""
    try:
        p1 = urlparse(url1)
        p2 = urlparse(url2)
        
        # Domain match
        if p1.netloc != p2.netloc:
            return 0.0
        
        # Path similarity (Jaccard su segmenti)
        # Use filter(None, ...) to remove empty strings from path segments
        path1_parts = set(filter(None, p1.path.strip('/').split('/')))
        path2_parts = set(filter(None, p2.path.strip('/').split('/')))
        
        # If both paths are empty (root URLs), they are identical
        if not path1_parts and not path2_parts:
            return 1.0
        
        # If only one path is empty, they are different
        if not path1_parts or not path2_parts:
            return 0.0
        
        intersection = len(path1_parts & path2_parts)
        union = len(path1_parts | path2_parts)
        
        return intersection / union if union > 0 else 0.0
    
    except Exception:
        return 0.0

async def aggregate_multi_engine(
    query: str,
    engines: List[str] = None,
    max_results: int = 15
) -> List[Dict[str, Any]]:
    """
    Aggrega risultati da motori multipli con deduplicazione.
    
    Args:
        query: Search query
        engines: Lista motori da usare (default: ["duckduckgo", "brave", "bing"])
        max_results: Max risultati finali dopo dedup
    
    Returns:
        Lista risultati deduplicated, ordinati per rilevanza composita
    """
    if engines is None:
        engines_str = os.getenv("SEARCH_ENGINES_ENABLED", "duckduckgo,brave,bing")
        engines = [e.strip() for e in engines_str.split(",")]
    
    # Parallel search su tutti i motori
    tasks = []
    task_engine_names = []  # Track which engine each task corresponds to
    
    if "brave" in engines:
        tasks.append(search_brave(query, BRAVE_COUNT))
        task_engine_names.append("brave")
    
    if "duckduckgo" in engines:
        # Import esistente core/web_search.py
        from core.web_search import search as ddg_search
        tasks.append(asyncio.to_thread(ddg_search, query, num=10))
        task_engine_names.append("duckduckgo")
    
    if "bing" in engines:
        # Import bing search from web_search.py
        from core.web_search import _search_bing_html
        tasks.append(asyncio.to_thread(_search_bing_html, query, 10))
        task_engine_names.append("bing")
    
    # Execute parallel
    results_by_engine = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Flatten results using zip for cleaner iteration
    all_results = []
    for engine_name, engine_results in zip(task_engine_names, results_by_engine):
        if isinstance(engine_results, Exception):
            log.warning(f"Engine {engine_name} failed: {engine_results}")
            continue
        
        if engine_results:
            all_results.extend(engine_results)
    
    # Deduplicazione fuzzy
    unique_results = []
    seen_urls = []
    
    for result in all_results:
        url = result.get("url", "")
        if not url:
            continue
        
        # Check se URL già visto (fuzzy match)
        is_duplicate = False
        for seen_url in seen_urls:
            if fuzzy_url_match(url, seen_url) > DEDUP_THRESHOLD:
                is_duplicate = True
                break
        
        if not is_duplicate:
            unique_results.append(result)
            seen_urls.append(url)
    
    log.info(
        f"Multi-engine search: {len(all_results)} raw → "
        f"{len(unique_results)} unique (dedup threshold={DEDUP_THRESHOLD})"
    )
    
    # Return top max_results
    return unique_results[:max_results]
