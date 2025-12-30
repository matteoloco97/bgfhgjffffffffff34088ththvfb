# core/search_providers/brave.py
"""
Brave Search API provider implementation.

Provides access to Brave Search API for web search results.
Requires BRAVE_API_KEY environment variable to be set.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Optional

from .base import BaseSearchProvider, ProviderResponse, SearchResult

log = logging.getLogger(__name__)


class BraveSearchProvider(BaseSearchProvider):
    """
    Brave Search API provider.
    
    Configuration:
        - BRAVE_API_KEY: API key for Brave Search (required)
        - BRAVE_SEARCH_ENABLED: Enable/disable Brave Search (default: "1")
    """
    
    name = "brave"
    
    # Brave Search API endpoint
    API_URL = "https://api.search.brave.com/res/v1/web/search"
    
    def __init__(self, timeout: float = 10.0):
        """Initialize Brave Search provider."""
        super().__init__(timeout=timeout)
        self.api_key = os.getenv("BRAVE_API_KEY", "")
        self.enabled = os.getenv("BRAVE_SEARCH_ENABLED", "1") == "1"
    
    def is_configured(self) -> bool:
        """Check if Brave Search is properly configured."""
        return bool(self.api_key) and self.enabled
    
    async def search(
        self,
        query: str,
        num_results: int = 10,
        language: str = "it"
    ) -> ProviderResponse:
        """
        Execute search using Brave Search API.
        
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
                error_message="Brave Search not configured (missing BRAVE_API_KEY)",
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
            
            # Map language code to Brave country code
            country_code = self._get_country_code(language)
            
            headers = {
                "Accept": "application/json",
                "Accept-Language": f"{language}",
                "X-Subscription-Token": self.api_key,
            }
            
            params = {
                "q": query.strip(),
                "count": min(num_results, 20),  # Brave API max is 20
                "country": country_code,
                "search_lang": language,
                "safesearch": "off",
            }
            
            async with client.get(
                self.API_URL,
                headers=headers,
                params=params,
                timeout=self.timeout,
            ) as response:
                elapsed_ms = int((time.perf_counter() - start_time) * 1000)
                
                if response.status != 200:
                    error_text = await response.text()
                    log.warning(f"Brave Search API error: {response.status} - {error_text[:200]}")
                    return ProviderResponse(
                        provider_name=self.name,
                        success=False,
                        error_message=f"API error: {response.status}",
                        response_time_ms=elapsed_ms,
                    )
                
                data = await response.json()
                results = self._parse_response(data)
                
                log.debug(f"Brave Search returned {len(results)} results in {elapsed_ms}ms")
                
                return ProviderResponse(
                    results=results,
                    provider_name=self.name,
                    success=True,
                    response_time_ms=elapsed_ms,
                )
                
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            log.warning(f"Brave Search error: {e}")
            return ProviderResponse(
                provider_name=self.name,
                success=False,
                error_message=str(e),
                response_time_ms=elapsed_ms,
            )
    
    def _parse_response(self, data: dict) -> list[SearchResult]:
        """
        Parse Brave Search API response.
        
        Parameters
        ----------
        data : dict
            API response JSON.
        
        Returns
        -------
        list[SearchResult]
            Parsed search results.
        """
        results = []
        
        # Parse web results
        web_results = data.get("web", {}).get("results", [])
        
        for idx, item in enumerate(web_results):
            url = item.get("url", "")
            title = item.get("title", "")
            snippet = item.get("description", "")
            
            if not url or not title:
                continue
            
            # Calculate basic score based on position (higher = better)
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
    
    def _get_country_code(self, language: str) -> str:
        """
        Map language code to Brave country code.
        
        Parameters
        ----------
        language : str
            Language code (e.g., "it", "en").
        
        Returns
        -------
        str
            Country code for Brave API.
        """
        mapping = {
            "it": "IT",
            "en": "US",
            "de": "DE",
            "fr": "FR",
            "es": "ES",
            "pt": "PT",
        }
        return mapping.get(language.lower(), "US")
