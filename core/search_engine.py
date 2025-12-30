# core/search_engine.py
"""
Multi-provider Search Engine with multilingual query expansion and trust scoring.

This module implements a robust search engine that:
- Supports multiple search providers with A→B→C fallback
- Expands queries in multiple languages (IT/EN by default)
- Normalizes results to a unified schema
- Scores and ranks results using trust configuration
- Provides detailed diagnostic logging

Configuration via environment variables:
- SEARCH_PROVIDER_PRIMARY: Primary search provider (default: brave)
- SEARCH_PROVIDER_SECONDARY: Secondary fallback provider (default: bing)
- SEARCH_PROVIDER_TERTIARY: Tertiary fallback provider (default: searxng)
- SEARCH_LANGS: Comma-separated language codes (default: it,en)
- SEARCH_MAX_RESULTS: Maximum results to return (default: 12)
- SEARCH_TIMEOUT: Provider timeout in seconds (default: 10)
- SEARCH_MIN_RESULTS_BEFORE_FALLBACK: Minimum results before fallback (default: 4)
"""

from __future__ import annotations

import os
import time
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from core.search_providers.base import (
    BaseSearchProvider,
    ProviderResponse,
    SearchResult,
)
from core.search_providers.brave import BraveSearchProvider
from core.search_providers.bing import BingSearchProvider
from core.search_providers.searxng import SearxngSearchProvider

log = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Provider configuration
SEARCH_PROVIDER_PRIMARY = os.getenv("SEARCH_PROVIDER_PRIMARY", "brave").lower()
SEARCH_PROVIDER_SECONDARY = os.getenv("SEARCH_PROVIDER_SECONDARY", "bing").lower()
SEARCH_PROVIDER_TERTIARY = os.getenv("SEARCH_PROVIDER_TERTIARY", "searxng").lower()

# Search parameters
SEARCH_LANGS = os.getenv("SEARCH_LANGS", "it,en").split(",")
SEARCH_MAX_RESULTS = int(os.getenv("SEARCH_MAX_RESULTS", "12"))
SEARCH_TIMEOUT = float(os.getenv("SEARCH_TIMEOUT", "10"))
SEARCH_MIN_RESULTS_BEFORE_FALLBACK = int(os.getenv("SEARCH_MIN_RESULTS_BEFORE_FALLBACK", "4"))


# =============================================================================
# Query Expansion
# =============================================================================

# Translation pairs for common terms (IT <-> EN)
TRANSLATION_PAIRS = {
    # Italian to English
    "it": {
        "prezzo": "price",
        "notizie": "news",
        "meteo": "weather",
        "oggi": "today",
        "come": "how",
        "cosa": "what",
        "quando": "when",
        "dove": "where",
        "perché": "why",
        "quanto": "how much",
        "migliore": "best",
        "guida": "guide",
        "tutorial": "tutorial",
        "recensione": "review",
        "confronto": "comparison",
    },
    # English to Italian
    "en": {
        "price": "prezzo",
        "news": "notizie",
        "weather": "meteo",
        "today": "oggi",
        "how": "come",
        "what": "cosa",
        "when": "quando",
        "where": "dove",
        "why": "perché",
        "how much": "quanto",
        "best": "migliore",
        "guide": "guida",
        "tutorial": "tutorial",
        "review": "recensione",
        "comparison": "confronto",
    },
}


def expand_query_multilingual(query: str, languages: List[str]) -> Dict[str, str]:
    """
    Expand query for multiple languages.
    
    Parameters
    ----------
    query : str
        Original query.
    languages : List[str]
        List of language codes.
    
    Returns
    -------
    Dict[str, str]
        Dictionary mapping language code to translated query.
    """
    queries = {}
    query_lower = query.lower()
    
    # Always include original query for the first language
    if languages:
        queries[languages[0]] = query
    
    # Check if query contains Italian words that can be translated
    translations_it_to_en = TRANSLATION_PAIRS.get("it", {})
    translations_en_to_it = TRANSLATION_PAIRS.get("en", {})
    
    # Detect if query looks Italian (contains known Italian words)
    has_italian = any(it_word in query_lower for it_word in translations_it_to_en.keys())
    # Detect if query looks English (contains known English words)
    has_english = any(en_word in query_lower for en_word in translations_en_to_it.keys())
    
    # If we have both IT and EN in languages, generate translations
    if "it" in languages and "en" in languages:
        # Add original as primary language
        if has_italian:
            queries["it"] = query
            # Translate Italian to English
            en_query = query
            for it_word, en_word in translations_it_to_en.items():
                if it_word in query_lower:
                    en_query = re.sub(
                        rf"\b{re.escape(it_word)}\b",
                        en_word,
                        en_query,
                        flags=re.IGNORECASE
                    )
            # Always add English variant if translation happened
            if en_query.lower() != query_lower:
                queries["en"] = en_query
            else:
                # No translation found, still search in English with same query
                queries["en"] = query
        elif has_english:
            queries["en"] = query
            # Translate English to Italian
            it_query = query
            for en_word, it_word in translations_en_to_it.items():
                if en_word in query_lower:
                    it_query = re.sub(
                        rf"\b{re.escape(en_word)}\b",
                        it_word,
                        it_query,
                        flags=re.IGNORECASE
                    )
            if it_query.lower() != query_lower:
                queries["it"] = it_query
            else:
                queries["it"] = query
        else:
            # No recognizable words, search same query in both languages
            queries["it"] = query
            queries["en"] = query
    else:
        # Single language mode
        for lang in languages:
            queries[lang] = query
    
    # Ensure at least one query is present
    if not queries:
        queries[languages[0] if languages else "it"] = query
    
    return queries


# =============================================================================
# Trust Scoring
# =============================================================================

@lru_cache(maxsize=1)
def _load_source_trust() -> Dict[str, Dict[str, float]]:
    """
    Load trust scores from config/source_trust.yaml.
    
    Returns
    -------
    Dict[str, Dict[str, float]]
        Mapping of category -> domain -> trust score.
    """
    try:
        import yaml
    except ImportError:
        log.warning("PyYAML not available, trust scoring disabled")
        return {}
    
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "config",
        "source_trust.yaml"
    )
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        
        trust_scores = {}
        
        # Parse categories
        categories = data.get("categories", {})
        for category_name, category_data in categories.items():
            category_scores = {}
            
            # Prefer domains get higher scores
            prefer = category_data.get("prefer", {})
            if isinstance(prefer, dict):
                for domain, score in prefer.items():
                    category_scores[domain.lower()] = float(score)
            
            # Allow domains
            allow = category_data.get("allow", {})
            if isinstance(allow, dict):
                for domain, score in allow.items():
                    if domain.lower() not in category_scores:
                        category_scores[domain.lower()] = float(score)
            
            trust_scores[category_name] = category_scores
        
        # Fallback scores
        fallback = data.get("fallback", {})
        fallback_scores = {}
        
        prefer = fallback.get("prefer", {})
        if isinstance(prefer, dict):
            for domain, score in prefer.items():
                fallback_scores[domain.lower()] = float(score)
        
        allow = fallback.get("allow", {})
        if isinstance(allow, dict):
            for domain, score in allow.items():
                if domain.lower() not in fallback_scores:
                    fallback_scores[domain.lower()] = float(score)
        
        trust_scores["_fallback"] = fallback_scores
        
        return trust_scores
    except Exception as e:
        log.warning(f"Failed to load source_trust.yaml: {e}")
        return {}


@lru_cache(maxsize=1)
def _load_source_policy() -> Dict[str, Any]:
    """
    Load source policy from config/source_policy.yaml.
    
    Returns
    -------
    Dict[str, Any]
        Source policy configuration.
    """
    try:
        import yaml
    except ImportError:
        log.warning("PyYAML not available, source policy disabled")
        return {}
    
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "config",
        "source_policy.yaml"
    )
    
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception as e:
        log.warning(f"Failed to load source_policy.yaml: {e}")
        return {}


def get_domain_trust_score(domain: str) -> float:
    """
    Get trust score for a domain.
    
    Parameters
    ----------
    domain : str
        Domain name (e.g., "wikipedia.org").
    
    Returns
    -------
    float
        Trust score (0.0-1.0).
    """
    if not domain:
        return 0.5
    
    domain = domain.lower()
    
    # Load trust config
    trust_config = _load_source_trust()
    
    # Check each category for domain
    for category_name, domains in trust_config.items():
        for trusted_domain, score in domains.items():
            if domain == trusted_domain or domain.endswith("." + trusted_domain):
                return score
    
    # Check source policy for additional scores
    policy = _load_source_policy()
    
    # High quality domains
    high_quality = policy.get("high_quality_domains", [])
    if domain in high_quality or any(domain.endswith("." + d) for d in high_quality):
        return 1.0
    
    # Medium quality domains
    medium_quality = policy.get("medium_quality_domains", [])
    if domain in medium_quality or any(domain.endswith("." + d) for d in medium_quality):
        return 0.8
    
    # Low quality domains
    low_quality = policy.get("low_quality_domains", [])
    if domain in low_quality or any(domain.endswith("." + d) for d in low_quality):
        return 0.5
    
    # Blocked domains
    blocked = policy.get("blocked_domains", [])
    if domain in blocked or any(domain.endswith("." + d) for d in blocked):
        return 0.0
    
    # Default score
    return 0.6


def get_max_per_domain() -> int:
    """
    Get maximum results per domain from policy.
    
    Returns
    -------
    int
        Maximum results per domain.
    """
    policy = _load_source_policy()
    dedup_config = policy.get("deduplication", {})
    return dedup_config.get("max_per_domain", 2)


# =============================================================================
# Search Engine
# =============================================================================

@dataclass
class SearchEngineResult:
    """
    Complete result from SearchEngine.
    """
    results: List[SearchResult] = field(default_factory=list)
    providers_tried: List[str] = field(default_factory=list)
    provider_used: str = ""
    languages: List[str] = field(default_factory=list)
    total_results: int = 0
    attempts: int = 0
    time_ms: int = 0
    top_domains: List[str] = field(default_factory=list)
    fallback_triggered: bool = False
    error: str = ""


class SearchEngine:
    """
    Multi-provider search engine with fallback, multilingual expansion, and trust scoring.
    
    Features:
    - Multi-provider support with A→B→C fallback
    - Multilingual query expansion (IT/EN default, extendable)
    - Result normalization to unified schema
    - Trust-based scoring and ranking
    - URL deduplication and max-per-domain limiting
    - Detailed diagnostic logging
    
    Usage:
        engine = SearchEngine()
        result = await engine.search("prezzo bitcoin")
        for r in result.results:
            print(f"{r.title} - {r.url} (score: {r.score})")
    """
    
    def __init__(
        self,
        providers: Optional[List[str]] = None,
        languages: Optional[List[str]] = None,
        max_results: int = SEARCH_MAX_RESULTS,
        timeout: float = SEARCH_TIMEOUT,
        min_results_before_fallback: int = SEARCH_MIN_RESULTS_BEFORE_FALLBACK,
    ):
        """
        Initialize SearchEngine.
        
        Parameters
        ----------
        providers : Optional[List[str]]
            Ordered list of provider names (default from env).
        languages : Optional[List[str]]
            List of language codes for query expansion (default from env).
        max_results : int
            Maximum results to return.
        timeout : float
            Provider timeout in seconds.
        min_results_before_fallback : int
            Minimum results before trying next provider.
        """
        # Configure providers
        if providers is None:
            providers = [
                SEARCH_PROVIDER_PRIMARY,
                SEARCH_PROVIDER_SECONDARY,
                SEARCH_PROVIDER_TERTIARY,
            ]
        self.provider_order = [p.lower().strip() for p in providers if p]
        
        # Configure languages
        self.languages = languages if languages else [l.strip() for l in SEARCH_LANGS]
        
        # Configure limits
        self.max_results = max_results
        self.timeout = timeout
        self.min_results_before_fallback = min_results_before_fallback
        self.max_per_domain = get_max_per_domain()
        
        # Initialize provider instances
        self._providers: Dict[str, BaseSearchProvider] = {
            "brave": BraveSearchProvider(timeout=timeout),
            "bing": BingSearchProvider(timeout=timeout),
            "searxng": SearxngSearchProvider(timeout=timeout),
        }
    
    def get_available_providers(self) -> List[str]:
        """
        Get list of configured and available providers.
        
        Returns
        -------
        List[str]
            List of available provider names.
        """
        available = []
        for name in self.provider_order:
            provider = self._providers.get(name)
            if provider and provider.is_configured():
                available.append(name)
        return available
    
    async def search(self, query: str) -> SearchEngineResult:
        """
        Execute search with fallback and multilingual expansion.
        
        Parameters
        ----------
        query : str
            Search query.
        
        Returns
        -------
        SearchEngineResult
            Complete search result with metadata.
        """
        start_time = time.perf_counter()
        
        # Initialize result
        result = SearchEngineResult(
            languages=self.languages,
        )
        
        if not query or not query.strip():
            result.error = "Empty query"
            log.warning("[SEARCH] Empty query provided")
            return result
        
        query = query.strip()
        
        # Get available providers
        available_providers = self.get_available_providers()
        
        if not available_providers:
            result.error = "No provider available"
            log.warning("[SEARCH] No search provider configured or available")
            return result
        
        # Expand query for multiple languages
        expanded_queries = expand_query_multilingual(query, self.languages)
        log.debug(f"[SEARCH] Expanded queries: {expanded_queries}")
        
        # Collect all results
        all_results: List[SearchResult] = []
        seen_urls: Set[str] = set()
        providers_tried: List[str] = []
        provider_used: str = ""
        attempts = 0
        
        # Try each provider in order
        for provider_name in available_providers:
            provider = self._providers.get(provider_name)
            if not provider:
                continue
            
            providers_tried.append(provider_name)
            attempts += 1
            
            # Search with each language variant
            for lang, lang_query in expanded_queries.items():
                try:
                    response = await provider.search(
                        lang_query,
                        num_results=self.max_results,
                        language=lang,
                    )
                    
                    if response.success and response.results:
                        # Add results that haven't been seen
                        for r in response.results:
                            if r.url not in seen_urls:
                                # Apply trust scoring: combine provider relevance score
                                # with domain trust score (50/50 weighting balances
                                # search relevance with source credibility)
                                trust_score = get_domain_trust_score(r.domain)
                                r.score = (r.score + trust_score) / 2.0
                                all_results.append(r)
                                seen_urls.add(r.url)
                        
                        if not provider_used:
                            provider_used = provider_name
                    
                except Exception as e:
                    log.warning(f"[SEARCH] Error with {provider_name}/{lang}: {e}")
            
            # Check if we have enough results
            if len(all_results) >= self.min_results_before_fallback:
                log.debug(f"[SEARCH] Got {len(all_results)} results from {provider_name}, stopping")
                break
            
            # Log that we're falling back to next provider
            log.info(f"[SEARCH] Fallback triggered, trying next provider")
        
        # Mark fallback_triggered if we used a provider other than the first one
        if len(providers_tried) > 1 and provider_used != providers_tried[0]:
            result.fallback_triggered = True
        
        # Apply deduplication and max-per-domain
        all_results = self._deduplicate_results(all_results)
        
        # Sort by score descending
        all_results.sort(key=lambda r: r.score, reverse=True)
        
        # Limit results
        all_results = all_results[:self.max_results]
        
        # Calculate timing
        elapsed_ms = int((time.perf_counter() - start_time) * 1000)
        
        # Build result
        result.results = all_results
        result.providers_tried = providers_tried
        result.provider_used = provider_used or (providers_tried[0] if providers_tried else "")
        result.total_results = len(all_results)
        result.attempts = attempts
        result.time_ms = elapsed_ms
        
        # Extract top domains
        domain_counts: Dict[str, int] = {}
        for r in all_results:
            domain_counts[r.domain] = domain_counts.get(r.domain, 0) + 1
        result.top_domains = sorted(
            domain_counts.keys(),
            key=lambda d: domain_counts[d],
            reverse=True
        )[:5]
        
        # Log diagnostic info
        log.info(
            f"[SEARCH] providers_tried={','.join(providers_tried)} "
            f"used={result.provider_used} "
            f"langs={','.join(self.languages)} "
            f"results={len(all_results)} "
            f"attempts={attempts} "
            f"time_ms={elapsed_ms}"
        )
        
        if result.top_domains:
            log.debug(f"[SEARCH] top_domains={','.join(result.top_domains)}")
        
        return result
    
    def _deduplicate_results(self, results: List[SearchResult]) -> List[SearchResult]:
        """
        Deduplicate results and apply max-per-domain limit.
        
        Parameters
        ----------
        results : List[SearchResult]
            Input results.
        
        Returns
        -------
        List[SearchResult]
            Deduplicated results.
        """
        seen_urls: Set[str] = set()
        domain_counts: Dict[str, int] = {}
        deduped: List[SearchResult] = []
        
        for r in results:
            # Skip duplicate URLs
            url_normalized = r.url.rstrip("/").lower()
            if url_normalized in seen_urls:
                continue
            
            # Apply max-per-domain
            if domain_counts.get(r.domain, 0) >= self.max_per_domain:
                continue
            
            seen_urls.add(url_normalized)
            domain_counts[r.domain] = domain_counts.get(r.domain, 0) + 1
            deduped.append(r)
        
        return deduped
    
    async def search_url_only(self, urls: List[str]) -> List[SearchResult]:
        """
        URL-only mode: when user includes links directly.
        
        Creates SearchResult objects from provided URLs without
        actually searching any provider.
        
        Parameters
        ----------
        urls : List[str]
            List of URLs from user input.
        
        Returns
        -------
        List[SearchResult]
            SearchResult objects for each URL.
        """
        results = []
        
        for url in urls:
            if not url or not url.strip():
                continue
            
            url = url.strip()
            
            try:
                parsed = urlparse(url)
                domain = parsed.hostname or ""
                if domain.startswith("www."):
                    domain = domain[4:]
                
                # Create result with basic info
                result = SearchResult(
                    title=f"User-provided: {domain}",
                    url=url,
                    snippet="",
                    domain=domain.lower(),
                    provider="url_only",
                    score=get_domain_trust_score(domain.lower()),
                )
                results.append(result)
                
            except Exception as e:
                log.warning(f"Failed to parse URL {url}: {e}")
        
        log.info(f"[SEARCH] url_only mode: {len(results)} URLs processed")
        return results


# =============================================================================
# Singleton factory
# =============================================================================

_search_engine_instance: Optional[SearchEngine] = None


def get_search_engine() -> SearchEngine:
    """
    Get singleton SearchEngine instance.
    
    Returns
    -------
    SearchEngine
        Configured SearchEngine instance.
    """
    global _search_engine_instance
    if _search_engine_instance is None:
        _search_engine_instance = SearchEngine()
    return _search_engine_instance
