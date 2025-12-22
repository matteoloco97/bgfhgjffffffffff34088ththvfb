#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/enhanced_web.py — Enhanced Web Search for QuantumDev Max

Features:
- SerpAPI integration for better search results
- DuckDuckGo fallback when SerpAPI unavailable
- Content extraction from URLs
- Smart synthesis with extractive summarization
- Query expansion for better recall

Author: Matteo (QuantumDev)
Version: 3.0.0 - Enhanced with smart synthesis
"""

from __future__ import annotations

import os
import logging
import asyncio
from typing import List, Dict, Any, Optional
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === ENV Configuration ===
SERPAPI_KEY = os.getenv("SERPAPI_KEY", "")
SEARCH_TIMEOUT = int(os.getenv("ENHANCED_SEARCH_TIMEOUT", "10"))
MAX_SNIPPET_LENGTH = int(os.getenv("MAX_SNIPPET_LENGTH", "500"))
# ENHANCEMENT: Increased default sources for better coverage
ENHANCED_SEARCH_SOURCES = int(os.getenv("ENHANCED_SEARCH_SOURCES", "8"))

USER_AGENT = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _extract_text_from_html(html_content: str) -> str:
    """
    Extract clean text from HTML content.
    
    Args:
        html_content: Raw HTML content
        
    Returns:
        Clean text content
    """
    try:
        soup = BeautifulSoup(html_content, 'lxml')
        
        # Remove script and style elements
        for script in soup(["script", "style", "noscript", "iframe"]):
            script.decompose()
        
        # Get text
        text = soup.get_text(separator=' ', strip=True)
        
        # Clean up whitespace
        lines = (line.strip() for line in text.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        text = ' '.join(chunk for chunk in chunks if chunk)
        
        return text
    except Exception as e:
        log.error(f"Failed to extract text from HTML: {e}")
        return ""


def _fetch_url_content(url: str, timeout: int = 10) -> Optional[str]:
    """
    Fetch content from URL.
    
    Args:
        url: URL to fetch
        timeout: Request timeout in seconds
        
    Returns:
        Page text content or None if failed
    """
    try:
        headers = {
            "User-Agent": USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        
        response = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
        response.raise_for_status()
        
        # Extract text from HTML
        text = _extract_text_from_html(response.text)
        
        return text
        
    except Exception as e:
        log.warning(f"Failed to fetch {url}: {e}")
        return None


def _create_snippet(text: str, max_length: int = MAX_SNIPPET_LENGTH) -> str:
    """
    Create a snippet from text.
    
    Args:
        text: Full text content
        max_length: Maximum snippet length
        
    Returns:
        Snippet text
    """
    if not text:
        return ""
    
    # Take first max_length characters
    snippet = text[:max_length]
    
    # Try to end at a sentence boundary
    if len(text) > max_length:
        # Find last sentence boundary
        for delimiter in ['. ', '! ', '? ', '\n']:
            last_idx = snippet.rfind(delimiter)
            if last_idx > max_length * 0.5:  # At least half the snippet
                snippet = snippet[:last_idx + 1]
                break
        else:
            # No sentence boundary found, add ellipsis
            snippet += "..."
    
    return snippet.strip()


def _search_with_serpapi(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Search using SerpAPI.
    
    Args:
        query: Search query
        k: Number of results
        
    Returns:
        List of search results
    """
    if not SERPAPI_KEY:
        log.warning("SERPAPI_KEY not configured, cannot use SerpAPI")
        return []
    
    try:
        # Try to import serpapi if available
        try:
            from serpapi import GoogleSearch
        except ImportError:
            log.warning("serpapi package not installed")
            return []
        
        params = {
            "q": query,
            "api_key": SERPAPI_KEY,
            "num": k,
            "hl": "it",
            "gl": "it",
        }
        
        search = GoogleSearch(params)
        results = search.get_dict()
        
        search_results = []
        for result in results.get("organic_results", [])[:k]:
            search_results.append({
                "title": result.get("title", ""),
                "url": result.get("link", ""),
                "snippet": result.get("snippet", ""),
            })
        
        log.info(f"SerpAPI returned {len(search_results)} results")
        return search_results
        
    except Exception as e:
        log.error(f"SerpAPI search failed: {e}")
        return []


def _search_with_duckduckgo(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Search using DuckDuckGo HTML endpoint.
    
    Args:
        query: Search query
        k: Number of results
        
    Returns:
        List of search results
    """
    try:
        from core.web_search import search as web_search_core
        
        # Use existing web_search module
        results = web_search_core(query, num=k)
        
        search_results = []
        for result in results[:k]:
            search_results.append({
                "title": result.get("title", ""),
                "url": result.get("url", ""),
                "snippet": result.get("snippet", ""),
            })
        
        log.info(f"DuckDuckGo returned {len(search_results)} results")
        return search_results
        
    except Exception as e:
        log.error(f"DuckDuckGo search failed: {e}")
        return []


async def enhanced_search(query: str, k: int = 5) -> List[Dict[str, Any]]:
    """
    Enhanced web search with content extraction and smart synthesis.
    
    Uses SerpAPI if available, otherwise falls back to DuckDuckGo.
    Fetches and extracts content from URLs to create better snippets.
    
    ENHANCEMENT v3.0: Now uses query expansion and smart synthesis.
    
    Args:
        query: Search query
        k: Number of results to return (default: 5, max: ENHANCED_SEARCH_SOURCES)
        
    Returns:
        List of search results with title, url, and snippet
    """
    if not query or not query.strip():
        log.warning("Empty search query")
        return []
    
    # Limit k to reasonable max
    k = min(k, ENHANCED_SEARCH_SOURCES)
    
    log.info(f"Enhanced search for: {query} (k={k})")
    
    # ENHANCEMENT: Try query expansion for better results
    search_queries = [query]
    try:
        from core.query_expander import get_query_expander
        expander = get_query_expander()
        expansion = expander.expand(query, max_expansions=3)
        if len(expansion.expanded) > 1:
            # Use original + best variant
            search_queries = [query, expansion.expanded[1]]
            log.info(f"Using expanded queries: {search_queries}")
    except Exception as e:
        log.debug(f"Query expansion not available: {e}")
    
    # Collect results from all query variants
    all_results: List[Dict[str, Any]] = []
    seen_urls: set = set()
    
    for search_query in search_queries:
        # Try SerpAPI first if available
        results = _search_with_serpapi(search_query, k)
        
        # Fallback to DuckDuckGo
        if not results:
            results = _search_with_duckduckgo(search_query, k)
        
        # Add unique results
        for result in results:
            url = result.get("url", "")
            if url and url not in seen_urls:
                all_results.append(result)
                seen_urls.add(url)
        
        # Stop if we have enough
        if len(all_results) >= k:
            break
    
    if not all_results:
        log.warning("No search results found")
        return []
    
    # Limit to k results
    all_results = all_results[:k]
    
    # Enhance results by fetching content asynchronously
    async def fetch_and_enhance(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Fetch and enhance a single result."""
        url = result.get("url", "")
        if not url:
            return None
        
        # Run sync request in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        text = await loop.run_in_executor(None, _fetch_url_content, url, SEARCH_TIMEOUT)
        
        if text:
            # ENHANCEMENT: Use smart synthesis for better snippets
            try:
                from core.smart_synthesis import get_smart_synthesizer
                synthesizer = get_smart_synthesizer()
                key_sentences = synthesizer.extract_key_sentences(
                    text, 
                    query=query,
                    top_n=3
                )
                if key_sentences:
                    snippet = " ".join(key_sentences[:2])  # Use top 2 sentences
                else:
                    snippet = _create_snippet(text)
            except Exception as e:
                log.debug(f"Smart synthesis not available: {e}")
                snippet = _create_snippet(text)
            
            return {
                "title": result.get("title", ""),
                "url": url,
                "snippet": snippet or result.get("snippet", ""),
                "text": text[:1000],  # Store first 1000 chars for further processing
            }
        else:
            # Use original snippet if fetch failed
            return {
                "title": result.get("title", ""),
                "url": url,
                "snippet": result.get("snippet", ""),
            }
    
    # Fetch all results concurrently
    tasks = [fetch_and_enhance(result) for result in all_results]
    enhanced_results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Filter out errors and None values
    final_results = []
    for result in enhanced_results:
        if isinstance(result, dict) and result:
            final_results.append(result)
        elif isinstance(result, Exception):
            log.warning(f"Error enhancing result: {result}")
    
    log.info(f"Enhanced search returned {len(final_results)} results")
    return final_results
