#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/query_expander.py — Smart Query Expansion for Better Search Results

Features:
- Semantic query reformulation
- Context-aware synonym expansion
- Domain-specific query enhancement
- Multi-language support (IT/EN)

Author: QuantumDev Enhancement
Version: 1.0.0
"""

from __future__ import annotations

import re
from typing import List, Set, Dict, Tuple
from datetime import datetime
from dataclasses import dataclass


@dataclass
class QueryExpansion:
    """Result of query expansion."""
    
    original: str
    expanded: List[str]
    domain: str
    confidence: float


class QueryExpander:
    """
    Espande query di ricerca in modo intelligente per migliorare recall e precision.
    
    Features:
    - Sinonimi contestuali (IT/EN)
    - Espansioni specifiche per dominio
    - Aggiunta di contesto temporale
    - Varianti ortografiche
    """
    
    # Sinonimi per topic comuni (IT/EN)
    SYNONYMS = {
        "prezzo": ["quotazione", "valore", "costo", "price", "cost"],
        "meteo": ["tempo", "previsioni", "weather", "forecast"],
        "notizie": ["news", "ultime", "aggiornamenti", "updates"],
        "risultati": ["punteggio", "score", "classifica", "standings"],
        "partita": ["match", "incontro", "game"],
        "bitcoin": ["btc", "bitcoin", "crypto"],
        "ethereum": ["eth", "ethereum"],
        "azioni": ["stock", "borsa", "shares"],
    }
    
    # Espansioni specifiche per dominio
    DOMAIN_EXPANSIONS = {
        "crypto": ["price", "market cap", "volume", "chart"],
        "weather": ["temperature", "precipitation", "forecast"],
        "sports": ["live", "score", "highlights", "standings"],
        "news": ["breaking", "latest", "today", "updates"],
        "finance": ["stock", "market", "trading", "index"],
    }
    
    # Keywords che indicano query temporalmente sensibili
    TEMPORAL_KEYWORDS = {
        "oggi", "adesso", "ora", "attualmente", "corrente",
        "today", "now", "current", "latest", "recent",
        "ieri", "yesterday", "scorso", "last",
    }
    
    # Keywords per rilevare dominio
    DOMAIN_INDICATORS = {
        "crypto": {"bitcoin", "btc", "ethereum", "eth", "crypto", "coin", "token"},
        "weather": {"meteo", "tempo", "weather", "forecast", "previsioni", "temperatura"},
        "sports": {"partita", "match", "risultati", "score", "classifica", "serie a", "champions"},
        "news": {"notizie", "news", "breaking", "cronaca", "ultime"},
        "finance": {"azioni", "borsa", "stock", "nasdaq", "mercato", "market"},
    }
    
    def __init__(self):
        """Initialize query expander."""
        self.current_year = datetime.now().year
    
    def detect_domain(self, query: str) -> str:
        """
        Rileva il dominio della query.
        
        Args:
            query: Query di ricerca
            
        Returns:
            Nome del dominio o "general"
        """
        q_lower = query.lower()
        
        # Conta match per ogni dominio
        domain_scores = {}
        for domain, keywords in self.DOMAIN_INDICATORS.items():
            score = sum(1 for kw in keywords if kw in q_lower)
            if score > 0:
                domain_scores[domain] = score
        
        if not domain_scores:
            return "general"
        
        # Ritorna dominio con score più alto
        return max(domain_scores.items(), key=lambda x: x[1])[0]
    
    def is_temporal_query(self, query: str) -> bool:
        """
        Verifica se la query richiede informazioni aggiornate.
        
        Args:
            query: Query di ricerca
            
        Returns:
            True se la query è temporalmente sensibile
        """
        q_lower = query.lower()
        return any(kw in q_lower for kw in self.TEMPORAL_KEYWORDS)
    
    def _add_temporal_context(self, query: str) -> List[str]:
        """
        Aggiunge contesto temporale alla query.
        
        Args:
            query: Query originale
            
        Returns:
            Lista di varianti con contesto temporale
        """
        variants = []
        
        # Se già ha keywords temporali, non duplicare
        if self.is_temporal_query(query):
            return variants
        
        # Aggiungi anno corrente per query potenzialmente temporali
        q_lower = query.lower()
        if any(kw in q_lower for kw in ["prezzo", "price", "quotazione", "risultati", "classifica"]):
            variants.append(f"{query} {self.current_year}")
        
        return variants
    
    def _add_domain_context(self, query: str, domain: str) -> List[str]:
        """
        Aggiunge contesto specifico del dominio.
        
        Args:
            query: Query originale
            domain: Dominio rilevato
            
        Returns:
            Lista di varianti con contesto di dominio
        """
        variants = []
        
        if domain == "general" or domain not in self.DOMAIN_EXPANSIONS:
            return variants
        
        # Aggiungi keywords di dominio se non presenti
        q_lower = query.lower()
        for keyword in self.DOMAIN_EXPANSIONS[domain][:2]:  # Max 2 keywords
            if keyword.lower() not in q_lower:
                variants.append(f"{query} {keyword}")
        
        return variants
    
    def _expand_with_synonyms(self, query: str, max_variants: int = 2) -> List[str]:
        """
        Espande query con sinonimi contestuali.
        
        Args:
            query: Query originale
            max_variants: Numero massimo di varianti per sinonimo
            
        Returns:
            Lista di varianti con sinonimi
        """
        variants = []
        q_lower = query.lower()
        
        # Per ogni parola nella query, cerca sinonimi
        for term, synonyms in self.SYNONYMS.items():
            if term in q_lower:
                # Aggiungi prime N varianti con sinonimi
                for syn in synonyms[:max_variants]:
                    # Sostituisci solo la prima occorrenza per evitare confusione
                    variant = q_lower.replace(term, syn, 1)
                    if variant != q_lower:
                        variants.append(variant)
        
        return variants
    
    def _add_location_context(self, query: str) -> List[str]:
        """
        Aggiunge contesto geografico dove rilevante.
        
        Args:
            query: Query originale
            
        Returns:
            Lista di varianti con contesto geografico
        """
        variants = []
        q_lower = query.lower()
        
        # Meteo senza città specificata → aggiungi "Italia"
        if "meteo" in q_lower or "weather" in q_lower:
            # Verifica che non ci sia già una città
            cities = {"roma", "milano", "napoli", "torino", "firenze", "venezia"}
            if not any(city in q_lower for city in cities):
                if "italia" not in q_lower and "italy" not in q_lower:
                    variants.append(f"{query} Italia")
        
        return variants
    
    def expand(
        self,
        query: str,
        max_expansions: int = 8,
        include_original: bool = True
    ) -> QueryExpansion:
        """
        Espande la query in modo intelligente.
        
        Args:
            query: Query originale
            max_expansions: Numero massimo di varianti da generare
            include_original: Se includere la query originale nei risultati
            
        Returns:
            QueryExpansion object con tutte le varianti
        """
        if not query or not query.strip():
            return QueryExpansion(
                original=query,
                expanded=[],
                domain="general",
                confidence=0.0
            )
        
        query = query.strip()
        domain = self.detect_domain(query)
        
        # Raccogli tutte le varianti
        all_variants: List[str] = []
        seen: Set[str] = set()
        
        # 1. Query originale
        if include_original:
            all_variants.append(query)
            seen.add(query.lower())
        
        # 2. Contesto temporale
        temporal_variants = self._add_temporal_context(query)
        for v in temporal_variants:
            if v.lower() not in seen:
                all_variants.append(v)
                seen.add(v.lower())
        
        # 3. Contesto di dominio
        domain_variants = self._add_domain_context(query, domain)
        for v in domain_variants:
            if v.lower() not in seen:
                all_variants.append(v)
                seen.add(v.lower())
        
        # 4. Sinonimi
        synonym_variants = self._expand_with_synonyms(query, max_variants=2)
        for v in synonym_variants:
            if v.lower() not in seen:
                all_variants.append(v)
                seen.add(v.lower())
        
        # 5. Contesto geografico
        location_variants = self._add_location_context(query)
        for v in location_variants:
            if v.lower() not in seen:
                all_variants.append(v)
                seen.add(v.lower())
        
        # Limita al numero massimo
        all_variants = all_variants[:max_expansions]
        
        # Calcola confidence basata su quante espansioni siamo riusciti a generare
        confidence = min(1.0, len(all_variants) / max(1, max_expansions))
        
        return QueryExpansion(
            original=query,
            expanded=all_variants,
            domain=domain,
            confidence=confidence
        )
    
    def get_best_variant(self, query: str) -> str:
        """
        Ottiene la migliore variante singola della query.
        
        Utile quando si vuole una sola query ottimizzata invece di multiple varianti.
        
        Args:
            query: Query originale
            
        Returns:
            La variante ritenuta migliore
        """
        expansion = self.expand(query, max_expansions=5)
        
        # Se abbiamo espansioni, preferisci quelle con contesto
        if len(expansion.expanded) > 1:
            # Preferisci varianti con anno per query temporali
            for variant in expansion.expanded[1:]:  # Skip original
                if str(self.current_year) in variant:
                    return variant
            
            # Altrimenti ritorna la prima espansione (dopo l'originale)
            return expansion.expanded[1]
        
        # Fallback alla query originale
        return query


# Singleton instance per riuso
_expander_instance: Optional[QueryExpander] = None


def get_query_expander() -> QueryExpander:
    """
    Ottiene l'istanza singleton del query expander.
    
    Returns:
        QueryExpander instance
    """
    global _expander_instance
    if _expander_instance is None:
        _expander_instance = QueryExpander()
    return _expander_instance


def expand_query(query: str, max_expansions: int = 8) -> List[str]:
    """
    Utility function per espandere una query.
    
    Args:
        query: Query da espandere
        max_expansions: Numero massimo di varianti
        
    Returns:
        Lista di query espanse
    """
    expander = get_query_expander()
    result = expander.expand(query, max_expansions=max_expansions)
    return result.expanded
