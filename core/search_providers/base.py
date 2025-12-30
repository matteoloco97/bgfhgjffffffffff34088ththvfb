# core/search_providers/base.py
"""
Base classes for search providers.

This module defines the abstract base class and data types
used by all search provider implementations.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

log = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """
    Unified search result schema.
    
    All providers must normalize their results to this format.
    """
    title: str
    url: str
    snippet: str = ""
    domain: str = ""
    provider: str = ""
    score: float = 0.0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary representation."""
        return {
            "title": self.title,
            "url": self.url,
            "snippet": self.snippet,
            "domain": self.domain,
            "provider": self.provider,
            "score": self.score,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> SearchResult:
        """Create SearchResult from dictionary."""
        return cls(
            title=data.get("title", ""),
            url=data.get("url", ""),
            snippet=data.get("snippet", ""),
            domain=data.get("domain", ""),
            provider=data.get("provider", ""),
            score=data.get("score", 0.0),
        )


@dataclass
class ProviderResponse:
    """
    Response from a search provider.
    
    Contains results and metadata about the search operation.
    """
    results: List[SearchResult] = field(default_factory=list)
    provider_name: str = ""
    success: bool = True
    error_message: str = ""
    response_time_ms: int = 0
    
    @property
    def result_count(self) -> int:
        """Number of results returned."""
        return len(self.results)


class BaseSearchProvider(ABC):
    """
    Abstract base class for search providers.
    
    All search provider implementations must inherit from this class
    and implement the required methods.
    """
    
    # Provider name (to be overridden by subclasses)
    name: str = "base"
    
    def __init__(self, timeout: float = 10.0):
        """
        Initialize the search provider.
        
        Parameters
        ----------
        timeout : float
            Request timeout in seconds.
        """
        self.timeout = timeout
    
    @abstractmethod
    async def search(
        self,
        query: str,
        num_results: int = 10,
        language: str = "it"
    ) -> ProviderResponse:
        """
        Execute a search query.
        
        Parameters
        ----------
        query : str
            The search query string.
        num_results : int
            Maximum number of results to return.
        language : str
            Language code for search results (e.g., "it", "en").
        
        Returns
        -------
        ProviderResponse
            Response containing search results and metadata.
        """
        pass
    
    @abstractmethod
    def is_configured(self) -> bool:
        """
        Check if the provider is properly configured.
        
        Returns
        -------
        bool
            True if provider has all required configuration.
        """
        pass
    
    def _extract_domain(self, url: str) -> str:
        """
        Extract domain from URL.
        
        Parameters
        ----------
        url : str
            Full URL.
        
        Returns
        -------
        str
            Domain name (e.g., "example.com").
        """
        if not url:
            return ""
        try:
            from urllib.parse import urlparse
            parsed = urlparse(url)
            host = parsed.hostname or ""
            # Remove www. prefix
            if host.startswith("www."):
                host = host[4:]
            return host.lower()
        except (ValueError, AttributeError):
            # ValueError for malformed URLs, AttributeError for None values
            return ""
    
    def _normalize_result(
        self,
        title: str,
        url: str,
        snippet: str = "",
        score: float = 0.0
    ) -> SearchResult:
        """
        Create a normalized SearchResult.
        
        Parameters
        ----------
        title : str
            Result title.
        url : str
            Result URL.
        snippet : str
            Result snippet/description.
        score : float
            Relevance score (0.0-1.0).
        
        Returns
        -------
        SearchResult
            Normalized search result.
        """
        return SearchResult(
            title=title.strip() if title else "",
            url=url.strip() if url else "",
            snippet=snippet.strip() if snippet else "",
            domain=self._extract_domain(url),
            provider=self.name,
            score=score,
        )
