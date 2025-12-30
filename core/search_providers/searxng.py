# core/search_providers/searxng.py
"""
SearXNG search provider implementation.

Provides access to self-hosted SearXNG instances for web search.
Requires SEARXNG_URL environment variable to be set.
SearXNG is a privacy-respecting, hackable metasearch engine.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Optional

from .base import BaseSearchProvider, ProviderResponse, SearchResult

log = logging.getLogger(__name__)


class SearxngSearchProvider(BaseSearchProvider):
    """
    SearXNG self-hosted search provider.
    
    Configuration:
        - SEARXNG_URL: Base URL of SearXNG instance (required)
        - SEARXNG_ENABLED: Enable/disable SearXNG (default: "1")
    
    Example SEARXNG_URL: http://localhost:8888 or http://searx.example.com
    """
    
    name = "searxng"
    
    def __init__(self, timeout: float = 10.0):
        """Initialize SearXNG provider."""
        super().__init__(timeout=timeout)
        self.base_url = os.getenv("SEARXNG_URL", "").rstrip("/")
        self.enabled = os.getenv("SEARXNG_ENABLED", "1") == "1"
    
    def is_configured(self) -> bool:
        """Check if SearXNG is properly configured."""
        return bool(self.base_url) and self.enabled
    
    async def search(
        self,
        query: str,
        num_results: int = 10,
        language: str = "it"
    ) -> ProviderResponse:
        """
        Execute search using SearXNG instance.
        
        Parameters
        ----------
        query : str
            Search query.
        num_results : int
            Maximum results to return.
        language : str
            Language code (e.g., "it", "en").
        
        Returns
        -------
        ProviderResponse
            Search results and metadata.
        """
        start_time = time.perf_counter()
        
        if not self.is_configured():
            return ProviderResponse(
                provider_name=self.name,
                success=False,
                error_message="SearXNG not configured (missing SEARXNG_URL)",
            )
        
        if not query or not query.strip():
            return ProviderResponse(
                provider_name=self.name,
                success=False,
                error_message="Empty query",
            )
        
        try:
            # Import HTTP client
            from core.async_http_client import get_http_client
            
            client = await get_http_client()
            if not client:
                return ProviderResponse(
                    provider_name=self.name,
                    success=False,
                    error_message="HTTP client not available",
                )
            
            # SearXNG search endpoint
            search_url = f"{self.base_url}/search"
            
            headers = {
                "Accept": "application/json",
            }
            
            params = {
                "q": query.strip(),
                "format": "json",
                "language": language,
                "pageno": 1,
                "categories": "general",
            }
            
            async with client.get(
                search_url,
                headers=headers,
                params=params,
                timeout=self.timeout,
            ) as response:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                
                if response.status != 200:
                    error_text = await response.text()
                    log.warning(f"SearXNG error: {response.status} - {error_text[:200]}")
                    return ProviderResponse(
                        provider_name=self.name,
                        success=False,
                        error_message=f"API error: {response.status}",
                        response_time_ms=elapsed_ms,
                    )
                
                data = await response.json()
                results = self._parse_response(data, num_results)
                
                log.debug(f"SearXNG returned {len(results)} results in {elapsed_ms}ms")
                
                return ProviderResponse(
                    results=results,
                    provider_name=self.name,
                    success=True,
                    response_time_ms=elapsed_ms,
                )
                
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            log.warning(f"SearXNG error: {e}")
            return ProviderResponse(
                provider_name=self.name,
                success=False,
                error_message=str(e),
                response_time_ms=elapsed_ms,
            )
    
    def _parse_response(self, data: dict, limit: int) -> list[SearchResult]:
        """
        Parse SearXNG API response.
        
        Parameters
        ----------
        data : dict
            API response JSON.
        limit : int
            Maximum number of results.
        
        Returns
        -------
        list[SearchResult]
            Parsed search results.
        """
        results = []
        
        # Parse results array
        items = data.get("results", [])
        
        for idx, item in enumerate(items[:limit]):
            url = item.get("url", "")
            title = item.get("title", "")
            snippet = item.get("content", "")
            
            if not url or not title:
                continue
            
            # SearXNG provides a score, use it if available
            raw_score = item.get("score", 0.0)
            # Normalize score (SearXNG scores can vary widely)
            if raw_score > 0:
                score = min(1.0, raw_score / 10.0)
            else:
                # Fall back to position-based scoring
                score = 1.0 - (idx * 0.05)
                score = max(0.1, min(1.0, score))
            
            result = self._normalize_result(
                title=title,
                url=url,
                snippet=snippet,
                score=score,
            )
            results.append(result)
        
        return results
