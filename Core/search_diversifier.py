#!/usr/bin/env python3
# core/search_diversifier.py — Multi-domain diversification per risultati web
# Garantisce varietà di prospettive evitando echo chamber effect

from __future__ import annotations
import os
import re
import logging
from typing import List, Dict, Any
from urllib.parse import urlparse
from collections import Counter

log = logging.getLogger(__name__)

# === CONFIG ===
DIVERSIFIER_MAX_PER_DOMAIN = int(os.getenv("DIVERSIFIER_MAX_PER_DOMAIN", "2"))
DIVERSIFIER_PRESERVE_TOP_N = int(os.getenv("DIVERSIFIER_PRESERVE_TOP_N", "3"))
DIVERSIFIER_MIN_UNIQUE_DOMAINS = int(os.getenv("DIVERSIFIER_MIN_UNIQUE_DOMAINS", "5"))


class SearchDiversifier:
    """
    Diversificazione intelligente risultati di ricerca.
    
    Strategia:
    1. Preserva top N per relevance (reranker score)
    2. Nel resto, limita URLs per dominio
    3. Fallback su risultati originali se troppo aggressivo
    
    Obiettivo: Max 2 URLs/dominio, min 5 domini unici in top 10
    """
    
    def __init__(self, max_per_domain: int = DIVERSIFIER_MAX_PER_DOMAIN):
        self.max_per_domain = max(1, max_per_domain)
        self.preserve_top_n = max(0, DIVERSIFIER_PRESERVE_TOP_N)
        self.min_unique_domains = max(1, DIVERSIFIER_MIN_UNIQUE_DOMAINS)
    
    def _extract_domain(self, url: str) -> str:
        """Estrae dominio base (es. example.com da www.example.com)"""
        try:
            parsed = urlparse(url)
            hostname = parsed.hostname or parsed.netloc or url
            
            # Rimuovi www
            hostname = re.sub(r'^www\.', '', hostname.lower())
            
            # Prendi ultimi 2 componenti (domain.tld)
            parts = hostname.split('.')
            if len(parts) >= 2:
                return '.'.join(parts[-2:])
            return hostname
        except:
            return url
    
    def diversify(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Applica diversificazione domini.
        
        Args:
            results: Lista risultati già rankata (con rerank_score opzionale)
        
        Returns:
            Lista diversificata mantenendo qualità
        """
        if not results:
            return results
        
        if len(results) <= self.preserve_top_n:
            # Troppo pochi risultati per diversificare
            return results
        
        # === STEP 1: Preserva top N (alta relevance) ===
        preserved = results[:self.preserve_top_n]
        to_process = results[self.preserve_top_n:]
        
        # Conta domini già nei preservati
        domain_counts: Dict[str, int] = {}
        for r in preserved:
            domain = self._extract_domain(r.get("url", ""))
            domain_counts[domain] = domain_counts.get(domain, 0) + 1
        
        # === STEP 2: Diversifica resto ===
        diversified = list(preserved)  # Copia preservati
        skipped = []
        
        for r in to_process:
            domain = self._extract_domain(r.get("url", ""))
            current_count = domain_counts.get(domain, 0)
            
            if current_count < self.max_per_domain:
                # Aggiungi
                diversified.append(r)
                domain_counts[domain] = current_count + 1
            else:
                # Skip ma conserva per fallback
                skipped.append(r)
        
        # === STEP 3: Verifica qualità ===
        unique_domains = len(set(domain_counts.keys()))
        
        # Se troppo aggressivo (pochi domini), aggiungi da skipped
        if unique_domains < self.min_unique_domains and skipped:
            log.info(f"Diversification too aggressive ({unique_domains} domains), adding from skipped")
            # Aggiungi da skipped fino a raggiungere min_unique_domains
            for r in skipped:
                domain = self._extract_domain(r.get("url", ""))
                if domain not in domain_counts:
                    diversified.append(r)
                    domain_counts[domain] = 1
                    unique_domains += 1
                    if unique_domains >= self.min_unique_domains:
                        break
        
        # === STEP 4: Log statistiche ===
        original_domains = len(set(self._extract_domain(r.get("url", "")) for r in results))
        log.info(
            f"Diversification: {len(results)} → {len(diversified)} results, "
            f"domains {original_domains} → {unique_domains}, "
            f"skipped {len(skipped)}"
        )
        
        return diversified
    
    def analyze_diversity(self, results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Analizza diversità domini in risultati.
        
        Returns:
            {
                "total_results": int,
                "unique_domains": int,
                "diversity_score": float,  # 0-1 (Shannon entropy normalizzato)
                "top_domains": [(domain, count), ...],
                "max_per_domain": int,
            }
        """
        if not results:
            return {
                "total_results": 0,
                "unique_domains": 0,
                "diversity_score": 0.0,
                "top_domains": [],
                "max_per_domain": 0,
            }
        
        domains = [self._extract_domain(r.get("url", "")) for r in results]
        domain_counts = Counter(domains)
        
        # Shannon entropy (normalizzato 0-1)
        import math
        n = len(domains)
        if n <= 1:
            entropy = 0.0
        else:
            probs = [count / n for count in domain_counts.values()]
            entropy = -sum(p * math.log2(p) for p in probs if p > 0)
            max_entropy = math.log2(n)  # Massima entropia possibile
            entropy = entropy / max_entropy if max_entropy > 0 else 0.0
        
        return {
            "total_results": len(results),
            "unique_domains": len(domain_counts),
            "diversity_score": round(entropy, 3),
            "top_domains": domain_counts.most_common(10),
            "max_per_domain": max(domain_counts.values()) if domain_counts else 0,
        }


# === Singleton globale ===
_GLOBAL_DIVERSIFIER: SearchDiversifier | None = None

def get_search_diversifier() -> SearchDiversifier:
    """Ottieni singleton diversifier"""
    global _GLOBAL_DIVERSIFIER
    if _GLOBAL_DIVERSIFIER is None:
        _GLOBAL_DIVERSIFIER = SearchDiversifier()
    return _GLOBAL_DIVERSIFIER
