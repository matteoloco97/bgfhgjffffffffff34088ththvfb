# core/search_providers/__init__.py
"""
Search providers package for multi-provider search engine.

This package contains search provider implementations for:
- Brave Search API
- Bing Search API  
- SearXNG (self-hosted fallback)
"""

from .base import BaseSearchProvider, SearchResult
from .brave import BraveSearchProvider
from .bing import BingSearchProvider
from .searxng import SearxngSearchProvider

__all__ = [
    "BaseSearchProvider",
    "SearchResult",
    "BraveSearchProvider",
    "BingSearchProvider",
    "SearxngSearchProvider",
]
