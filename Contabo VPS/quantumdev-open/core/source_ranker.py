# core/source_ranker.py - NEW FILE

from typing import List, Dict, Any
from urllib.parse import urlparse
import re

class SourceQualityRanker:
    """
    Ranking avanzato delle fonti basato su autorevolezza e affidabilità.
    """
    
    # Domini autorevoli per categoria
    TRUSTED_DOMAINS = {
        "news": {
            "ilsole24ore.com": 0.95,
            "corriere.it": 0.90,
            "repubblica.it": 0.85,
            "ansa.it": 0.95,
            "reuters.com": 0.95,
            "bbc.com": 0.90,
            "ft.com": 0.95
        },
        "tech": {
            "github.com": 0.90,
            "stackoverflow.com": 0.85,
            "developer.mozilla.org": 0.95,
            "docs.python.org": 0.95,
            "techcrunch.com": 0.80
        },
        "finance": {
            "bloomberg.com": 0.95,
            "ft.com": 0.95,
            "wsj.com": 0.90,
            "investing.com": 0.80,
            "yahoo.com/finance": 0.75
        },
        "academic": {
            "arxiv.org": 0.90,
            "scholar.google.com": 0.85,
            "nature.com": 0.95,
            "science.org": 0.95
        }
    }
    
    def rank_sources(
        self, 
        results: List[Dict[str, Any]],
        query: str = ""
    ) -> List[Dict[str, Any]]:
        """
        Ranka fonti basandosi su:
        1. Autorevolezza dominio
        2. Freshness (HTTPS, SSL)
        3. Rilevanza snippet
        4. Lunghezza/qualità snippet
        """
        scored = []
        
        for r in results:
            url = r.get('url', '')
            domain = urlparse(url).netloc.lower().replace('www.', '')
            
            # Score base da trusted domains
            base_score = 0.5
            for category, domains in self.TRUSTED_DOMAINS.items():
                if domain in domains:
                    base_score = domains[domain]
                    break
            
            # Bonus HTTPS
            if url.startswith('https://'):
                base_score += 0.05
            
            # Snippet quality
            snippet = r.get('snippet', '')
            if len(snippet) > 100:
                base_score += 0.05
            
            # Relevance (keywords in snippet)
            if query:
                query_terms = set(query.lower().split())
                snippet_lower = snippet.lower()
                matches = sum(1 for term in query_terms if term in snippet_lower and len(term) > 3)
                relevance = matches / max(1, len(query_terms))
                base_score += relevance * 0.1
            
            scored.append({
                **r,
                "quality_score": round(min(1.0, base_score), 3)
            })
        
        # Sort by quality score
        scored.sort(key=lambda x: x['quality_score'], reverse=True)
        
        return scored
    
    def filter_low_quality(
        self,
        sources: List[Dict[str, Any]],
        threshold: float = 0.4
    ) -> List[Dict[str, Any]]:
        """Filtra fonti sotto threshold qualitativo."""
        return [
            s for s in sources
            if s.get('quality_score', 0.5) >= threshold
        ]
