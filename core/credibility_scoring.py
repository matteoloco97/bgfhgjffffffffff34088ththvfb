#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/credibility_scoring.py — Advanced Source Credibility Scoring

Implements comprehensive source credibility assessment:
- Domain authority scoring
- Content freshness analysis
- Cross-source verification
- Fact-checking indicators
- Confidence level calculation

Author: QuantumDev Enhancement
Version: 1.0.0
"""

from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from urllib.parse import urlparse
from datetime import datetime

log = logging.getLogger(__name__)


@dataclass
class CredibilityScore:
    """Credibility assessment for a source."""
    overall_score: float  # 0.0 - 1.0
    domain_authority: float
    content_quality: float
    freshness_score: float
    bias_indicator: str  # "neutral", "slight", "moderate", "high"
    verification_status: str  # "verified", "unverified", "disputed"
    confidence_level: str  # "high", "medium", "low"
    warnings: List[str] = field(default_factory=list)


class CredibilityScorer:
    """
    Scores source credibility using multiple factors.
    
    Factors considered:
    - Domain authority (known reliable sources)
    - Content quality signals
    - Freshness of information
    - Cross-verification with other sources
    - Bias indicators
    """
    
    # Domain authority tiers (0.0 - 1.0)
    DOMAIN_AUTHORITY = {
        # Tier 1: Highly authoritative (0.9-1.0)
        "gov.it": 0.95, "governo.it": 0.95, "ansa.it": 0.92,
        "reuters.com": 0.95, "bbc.com": 0.90, "bbc.co.uk": 0.90,
        "ft.com": 0.92, "bloomberg.com": 0.92,
        "nature.com": 0.95, "science.org": 0.95, "arxiv.org": 0.90,
        "who.int": 0.95, "cdc.gov": 0.95, "nih.gov": 0.95,
        "europa.eu": 0.95, "un.org": 0.95,
        
        # Tier 2: Reliable news (0.75-0.89)
        "corriere.it": 0.85, "repubblica.it": 0.80, "ilsole24ore.com": 0.88,
        "nytimes.com": 0.88, "washingtonpost.com": 0.85, "theguardian.com": 0.82,
        "economist.com": 0.90, "forbes.com": 0.78,
        "ilfattoquotidiano.it": 0.75, "lastampa.it": 0.80,
        
        # Tier 3: Tech/specialized (0.70-0.84)
        "github.com": 0.85, "stackoverflow.com": 0.82,
        "developer.mozilla.org": 0.90, "docs.python.org": 0.90,
        "techcrunch.com": 0.75, "wired.com": 0.78, "arstechnica.com": 0.80,
        "coinmarketcap.com": 0.75, "coindesk.com": 0.72,
        
        # Tier 4: General reference (0.60-0.74)
        "wikipedia.org": 0.70, "investopedia.com": 0.72,
        "treccani.it": 0.80, "britannica.com": 0.82,
        
        # Tier 5: Lower reliability (0.40-0.59)
        "medium.com": 0.50, "substack.com": 0.50,
        "reddit.com": 0.45, "quora.com": 0.45,
        "facebook.com": 0.30, "twitter.com": 0.35, "x.com": 0.35,
    }
    
    # Bias indicators by domain
    BIAS_INDICATORS = {
        # Neutral/Low bias
        "reuters.com": "neutral", "ansa.it": "neutral", "bbc.com": "neutral",
        "ft.com": "neutral", "economist.com": "slight",
        
        # Slight bias
        "corriere.it": "slight", "repubblica.it": "slight",
        "nytimes.com": "slight", "washingtonpost.com": "slight",
        
        # Moderate bias
        "huffpost.com": "moderate", "foxnews.com": "moderate",
        "ilgiornale.it": "moderate", "liberoquotidiano.it": "moderate",
    }
    
    # Keywords indicating unreliable content
    UNRELIABLE_SIGNALS = [
        r'\b(sponsored|adv|pubblicità|promozionale)\b',
        r'\b(questo articolo contiene link affiliati)\b',
        r'\b(breaking|esclusivo|shock)\b',
        r'\b(non crederai|incredibile)\b',
        r'\b(fake|bufala|hoax)\b',
    ]
    
    # Keywords indicating verified/quality content
    QUALITY_SIGNALS = [
        r'\b(studio|ricerca|analisi)\b',
        r'\b(secondo\s+(?:gli esperti|i ricercatori|gli scienziati))\b',
        r'\b(fonte|fonti|citazione)\b',
        r'\b(peer[- ]?reviewed)\b',
        r'\b(ufficiale|confermato)\b',
    ]
    
    def __init__(self):
        """Initialize credibility scorer."""
        self._domain_cache: Dict[str, float] = {}
    
    def _extract_domain(self, url: str) -> str:
        """Extract base domain from URL."""
        try:
            parsed = urlparse(url)
            domain = parsed.netloc.lower().replace('www.', '')
            return domain
        except Exception:
            return ""
    
    def _get_domain_authority(self, domain: str) -> float:
        """
        Get authority score for a domain.
        
        Args:
            domain: Domain name
            
        Returns:
            Authority score 0.0-1.0
        """
        if not domain:
            return 0.3
        
        # Direct match
        if domain in self.DOMAIN_AUTHORITY:
            return self.DOMAIN_AUTHORITY[domain]
        
        # Check subdomains (e.g., news.bbc.com → bbc.com)
        parts = domain.split('.')
        for i in range(len(parts) - 1):
            parent = '.'.join(parts[i:])
            if parent in self.DOMAIN_AUTHORITY:
                return self.DOMAIN_AUTHORITY[parent] * 0.95  # Slight discount for subdomain
        
        # Default score based on TLD
        if domain.endswith('.gov') or domain.endswith('.gov.it'):
            return 0.85
        elif domain.endswith('.edu') or domain.endswith('.ac.uk'):
            return 0.80
        elif domain.endswith('.org'):
            return 0.60
        else:
            return 0.50  # Default for unknown domains
    
    def _assess_content_quality(
        self,
        text: str,
        title: str = ""
    ) -> Tuple[float, List[str]]:
        """
        Assess content quality based on text signals.
        
        Args:
            text: Content text
            title: Content title
            
        Returns:
            (quality_score, warnings)
        """
        if not text and not title:
            return 0.3, ["Contenuto non disponibile"]
        
        full_text = f"{title} {text}".lower()
        quality_score = 0.5
        warnings = []
        
        # Check for unreliable signals (negative)
        for pattern in self.UNRELIABLE_SIGNALS:
            if re.search(pattern, full_text, re.IGNORECASE):
                quality_score -= 0.15
                warnings.append("Segnali di contenuto promozionale o sensazionalistico")
                break
        
        # Check for quality signals (positive)
        quality_signal_count = 0
        for pattern in self.QUALITY_SIGNALS:
            if re.search(pattern, full_text, re.IGNORECASE):
                quality_signal_count += 1
        
        if quality_signal_count >= 2:
            quality_score += 0.2
        elif quality_signal_count >= 1:
            quality_score += 0.1
        
        # Check content length (very short content is suspicious)
        word_count = len(text.split())
        if word_count < 20:
            quality_score -= 0.1
            warnings.append("Contenuto troppo breve")
        elif word_count > 200:
            quality_score += 0.05
        
        # Check for numbers/data (indicates factual content)
        if re.search(r'\d+', text):
            quality_score += 0.05
        
        return min(1.0, max(0.0, quality_score)), warnings
    
    def _assess_freshness(
        self,
        text: str,
        url: str = ""
    ) -> Tuple[float, str]:
        """
        Assess content freshness.
        
        Args:
            text: Content text
            url: Source URL
            
        Returns:
            (freshness_score, timestamp_hint)
        """
        current_year = datetime.now().year
        
        # Look for year mentions in text
        years_found = re.findall(r'\b(20[0-2]\d)\b', text)
        if years_found:
            most_recent = max(int(y) for y in years_found)
            age = current_year - most_recent
            
            if age == 0:
                return 1.0, f"Riferimenti a {current_year}"
            elif age == 1:
                return 0.9, f"Riferimenti a {current_year - 1}"
            elif age <= 2:
                return 0.7, f"Riferimenti a {most_recent}"
            elif age <= 5:
                return 0.5, f"Riferimenti a {most_recent}"
            else:
                return 0.3, f"Contenuto potenzialmente datato ({most_recent})"
        
        # Default: unknown freshness
        return 0.6, "Freschezza non determinabile"
    
    def _get_bias_indicator(self, domain: str) -> str:
        """Get bias indicator for a domain."""
        return self.BIAS_INDICATORS.get(domain, "unknown")
    
    def score_source(
        self,
        url: str,
        title: str = "",
        text: str = ""
    ) -> CredibilityScore:
        """
        Calculate comprehensive credibility score for a source.
        
        Args:
            url: Source URL
            title: Content title
            text: Content text
            
        Returns:
            CredibilityScore with all metrics
        """
        domain = self._extract_domain(url)
        
        # Calculate individual scores
        domain_authority = self._get_domain_authority(domain)
        content_quality, warnings = self._assess_content_quality(text, title)
        freshness_score, freshness_note = self._assess_freshness(text, url)
        bias_indicator = self._get_bias_indicator(domain)
        
        # Add freshness note to warnings if notable
        if freshness_score < 0.5:
            warnings.append(freshness_note)
        
        # Calculate overall score (weighted average)
        overall_score = (
            domain_authority * 0.40 +
            content_quality * 0.35 +
            freshness_score * 0.25
        )
        
        # Determine verification status
        if domain_authority >= 0.85 and content_quality >= 0.6:
            verification_status = "verified"
        elif domain_authority >= 0.60:
            verification_status = "unverified"
        else:
            verification_status = "disputed"
        
        # Determine confidence level
        if overall_score >= 0.75:
            confidence_level = "high"
        elif overall_score >= 0.50:
            confidence_level = "medium"
        else:
            confidence_level = "low"
        
        return CredibilityScore(
            overall_score=round(overall_score, 3),
            domain_authority=round(domain_authority, 3),
            content_quality=round(content_quality, 3),
            freshness_score=round(freshness_score, 3),
            bias_indicator=bias_indicator,
            verification_status=verification_status,
            confidence_level=confidence_level,
            warnings=warnings
        )
    
    def score_sources(
        self,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Score multiple sources and add credibility metrics.
        
        Args:
            sources: List of source dicts
            
        Returns:
            Sources with credibility scores added
        """
        scored_sources = []
        
        for source in sources:
            score = self.score_source(
                url=source.get('url', ''),
                title=source.get('title', ''),
                text=source.get('snippet', '') or source.get('text', '')
            )
            
            scored_source = {
                **source,
                'credibility': {
                    'overall_score': score.overall_score,
                    'domain_authority': score.domain_authority,
                    'content_quality': score.content_quality,
                    'freshness_score': score.freshness_score,
                    'confidence_level': score.confidence_level,
                    'verification_status': score.verification_status,
                    'bias_indicator': score.bias_indicator,
                    'warnings': score.warnings,
                }
            }
            scored_sources.append(scored_source)
        
        # Sort by overall score
        scored_sources.sort(
            key=lambda x: x['credibility']['overall_score'],
            reverse=True
        )
        
        return scored_sources
    
    def filter_reliable(
        self,
        sources: List[Dict[str, Any]],
        min_score: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Filter sources to keep only reliable ones.
        
        Args:
            sources: List of scored sources
            min_score: Minimum credibility score
            
        Returns:
            Filtered list of reliable sources
        """
        scored = self.score_sources(sources)
        return [
            s for s in scored
            if s['credibility']['overall_score'] >= min_score
        ]
    
    def get_consensus_confidence(
        self,
        sources: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Calculate overall confidence based on source agreement.
        
        Args:
            sources: List of scored sources
            
        Returns:
            Dict with consensus metrics
        """
        if not sources:
            return {
                'confidence': 0.0,
                'level': 'none',
                'source_count': 0,
                'message': 'Nessuna fonte disponibile'
            }
        
        scored = self.score_sources(sources)
        scores = [s['credibility']['overall_score'] for s in scored]
        
        avg_score = sum(scores) / len(scores)
        high_quality_count = sum(1 for s in scores if s >= 0.7)
        
        # Consensus confidence considers:
        # 1. Average source quality
        # 2. Number of high-quality sources
        # 3. Score consistency (low variance = higher confidence)
        
        if len(scores) > 1:
            variance = sum((s - avg_score) ** 2 for s in scores) / len(scores)
            consistency_bonus = max(0, 0.2 - variance)
        else:
            consistency_bonus = 0
        
        source_count_bonus = min(0.1, len(scored) * 0.02)
        
        consensus_confidence = min(1.0, avg_score + consistency_bonus + source_count_bonus)
        
        if consensus_confidence >= 0.75:
            level = 'high'
            message = 'Fonti multiple e affidabili confermano'
        elif consensus_confidence >= 0.50:
            level = 'medium'
            message = 'Informazioni supportate da alcune fonti'
        else:
            level = 'low'
            message = 'Fonti limitate o di bassa affidabilità'
        
        return {
            'confidence': round(consensus_confidence, 3),
            'level': level,
            'source_count': len(scored),
            'high_quality_sources': high_quality_count,
            'average_score': round(avg_score, 3),
            'message': message
        }


# === Singleton Instance ===
_scorer_instance: Optional[CredibilityScorer] = None


def get_credibility_scorer() -> CredibilityScorer:
    """Get or create CredibilityScorer singleton."""
    global _scorer_instance
    if _scorer_instance is None:
        _scorer_instance = CredibilityScorer()
    return _scorer_instance


def score_source_credibility(
    url: str,
    title: str = "",
    text: str = ""
) -> Dict[str, Any]:
    """
    Utility function to score a single source.
    
    Args:
        url: Source URL
        title: Content title
        text: Content text
        
    Returns:
        Dict with credibility metrics
    """
    scorer = get_credibility_scorer()
    score = scorer.score_source(url, title, text)
    
    return {
        'overall_score': score.overall_score,
        'domain_authority': score.domain_authority,
        'content_quality': score.content_quality,
        'freshness_score': score.freshness_score,
        'confidence_level': score.confidence_level,
        'verification_status': score.verification_status,
        'bias_indicator': score.bias_indicator,
        'warnings': score.warnings,
    }
