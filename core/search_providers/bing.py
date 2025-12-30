# core/search_providers/bing.py
"""
Bing Search API provider implementation.

Provides access to Bing Web Search API for web search results.
Requires BING_API_KEY environment variable to be set.
"""

from __future__ import annotations

import os
import time
import logging
from typing import Optional

from .base import BaseSearchProvider, ProviderResponse, SearchResult

log = logging.getLogger(__name__)


class BingSearchProvider(BaseSearchProvider):
    """
    Bing Web Search API provider.
    
    Configuration:
        - BING_API_KEY: API key for Bing Search (required)
        - BING_SEARCH_ENABLED: Enable/disable Bing Search (default: "1")
    """
    
    name = "bing"
    
    # Bing Search API endpoint
    API_URL = "https://api.bing.microsoft.com/v7.0/search"
    
    def __init__(self, timeout: float = 10.0):
        """Initialize Bing Search provider."""
        super().__init__(timeout=timeout)
        self.api_key = os.getenv("BING_API_KEY", "")
        self.enabled = os.getenv("BING_SEARCH_ENABLED", "1") == "1"
    
    def is_configured(self) -> bool:
        """Check if Bing Search is properly configured."""
        return bool(self.api_key) and self.enabled
    
    async def search(
        self,
        query: str,
        num_results: int = 10,
        language: str = "it"
    ) -> ProviderResponse:
        """
        Execute search using Bing Web Search API.
        
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
                error_message="Bing Search not configured (missing BING_API_KEY)",
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
            
            # Build headers and params
            market = self._get_market(language)
            
            headers = {
                "Ocp-Apim-Subscription-Key": self.api_key,
                "Accept": "application/json",
            }
            
            params = {
                "q": query.strip(),
                "count": min(num_results, 50),  # Bing API max is 50
                "mkt": market,
                "setLang": language,
                "safeSearch": "Off",
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
                    log.warning(f"Bing Search API error: {response.status} - {error_text[:200]}")
                    return ProviderResponse(
                        provider_name=self.name,
                        success=False,
                        error_message=f"API error: {response.status}",
                        response_time_ms=elapsed_ms,
                    )
                
                data = await response.json()
                results = self._parse_response(data)
                
                log.debug(f"Bing Search returned {len(results)} results in {elapsed_ms}ms")
                
                return ProviderResponse(
                    results=results,
                    provider_name=self.name,
                    success=True,
                    response_time_ms=elapsed_ms,
                )
                
        except Exception as e:
            elapsed_ms = int((time.perf_counter() - start_time) * 1000)
            log.warning(f"Bing Search error: {e}")
            return ProviderResponse(
                provider_name=self.name,
                success=False,
                error_message=str(e),
                response_time_ms=elapsed_ms,
            )
    
    def _parse_response(self, data: dict) -> list[SearchResult]:
        """
        Parse Bing Search API response.
        
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
        
        # Parse web pages
        web_pages = data.get("webPages", {}).get("value", [])
        
        for idx, item in enumerate(web_pages):
            url = item.get("url", "")
            title = item.get("name", "")
            snippet = item.get("snippet", "")
            
            if not url or not title:
                continue
            
            # Calculate basic score based on position
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
    
    def _get_market(self, language: str) -> str:
        """
        Map language code to Bing market code.
        
        Parameters
        ----------
        language : str
            Language code (e.g., "it", "en").
        
        Returns
        -------
        str
            Market code for Bing API.
        """
        mapping = {
            "it": "it-IT",
            "en": "en-US",
            "de": "de-DE",
            "fr": "fr-FR",
            "es": "es-ES",
            "pt": "pt-PT",
        }
        return mapping.get(language.lower(), "en-US")
