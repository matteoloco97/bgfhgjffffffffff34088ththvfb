#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/smart_synthesis.py — Intelligent Content Synthesis for Web Results

Features:
- Extractive summarization with key sentence detection
- Multi-document synthesis with deduplication
- Quality scoring for content relevance
- Context-aware snippet generation

Author: QuantumDev Enhancement
Version: 1.0.0
"""

from __future__ import annotations

import re
import logging
from typing import List, Dict, Any, Tuple, Set
from collections import Counter
from dataclasses import dataclass

log = logging.getLogger(__name__)


@dataclass
class SynthesisResult:
    """Result of content synthesis."""
    
    summary: str
    key_points: List[str]
    sources: List[Dict[str, str]]
    confidence: float


class SmartSynthesizer:
    """
    Sintetizza intelligentemente contenuti da multiple fonti web.
    
    Features:
    - Estrazione frasi chiave basata su scoring
    - Deduplicazione semantica
    - Ranking per rilevanza
    - Sintesi multi-documento
    """
    
    # Stop words per italiano e inglese
    STOP_WORDS = {
        # Italiano
        "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
        "di", "a", "da", "in", "con", "su", "per", "tra", "fra",
        "e", "ed", "o", "od", "ma", "però", "anche", "né",
        "non", "più", "meno", "molto", "poco", "tanto", "quanto",
        "che", "chi", "cui", "quale", "quando", "dove", "come", "perché",
        "del", "dello", "della", "dei", "degli", "delle",
        "al", "allo", "alla", "ai", "agli", "alle",
        "dal", "dallo", "dalla", "dai", "dagli", "dalle",
        "nel", "nello", "nella", "nei", "negli", "nelle",
        "sul", "sullo", "sulla", "sui", "sugli", "sulle",
        # Inglese
        "the", "a", "an", "and", "or", "but", "in", "on", "at", "to", "for",
        "of", "with", "by", "from", "up", "about", "into", "through", "during",
        "is", "are", "was", "were", "be", "been", "being", "have", "has", "had",
        "do", "does", "did", "will", "would", "should", "could", "may", "might",
        "this", "that", "these", "those", "i", "you", "he", "she", "it", "we", "they",
    }
    
    def __init__(self):
        """Initialize synthesizer."""
        pass
    
    def _extract_keywords(self, text: str, top_n: int = 10) -> List[str]:
        """
        Estrae keywords più importanti dal testo.
        
        Args:
            text: Testo da analizzare
            top_n: Numero di keywords da estrarre
            
        Returns:
            Lista di keywords ordinate per importanza
        """
        # Tokenize e pulisci
        words = re.findall(r'\b\w+\b', text.lower())
        
        # Filtra stop words e parole troppo corte
        filtered = [
            w for w in words
            if len(w) > 3 and w not in self.STOP_WORDS
        ]
        
        # Conta frequenze
        counter = Counter(filtered)
        
        # Ritorna top N
        return [word for word, _ in counter.most_common(top_n)]
    
    def _score_sentence(
        self,
        sentence: str,
        keywords: List[str],
        position: int,
        total_sentences: int
    ) -> float:
        """
        Assegna uno score a una frase basato su vari fattori.
        
        Args:
            sentence: Frase da valutare
            keywords: Keywords importanti del documento
            position: Posizione della frase nel documento (0-indexed)
            total_sentences: Numero totale di frasi nel documento
            
        Returns:
            Score della frase (0.0 - 1.0)
        """
        score = 0.0
        s_lower = sentence.lower()
        
        # 1. Presenza di keywords (peso maggiore)
        keyword_count = sum(1 for kw in keywords if kw in s_lower)
        if keywords:
            keyword_score = keyword_count / len(keywords)
            score += keyword_score * 0.5
        
        # 2. Posizione nel documento (inizio e fine più importanti)
        if total_sentences > 0:
            # Prima frase ha bonus
            if position == 0:
                score += 0.2
            # Ultime frasi hanno bonus minore
            elif position >= total_sentences - 2:
                score += 0.1
        
        # 3. Lunghezza della frase (preferisci frasi di lunghezza media)
        words = sentence.split()
        word_count = len(words)
        if 10 <= word_count <= 30:
            score += 0.2
        elif 5 <= word_count <= 40:
            score += 0.1
        
        # 4. Presenza di numeri (spesso indicano fatti concreti)
        if re.search(r'\d+', sentence):
            score += 0.1
        
        # 5. Presenza di entità (nomi propri capitalizzati)
        capitals = sum(1 for w in words if w and w[0].isupper() and len(w) > 1)
        if capitals >= 2:
            score += 0.1
        
        return min(1.0, score)
    
    def _split_sentences(self, text: str) -> List[str]:
        """
        Divide il testo in frasi.
        
        Args:
            text: Testo da dividere
            
        Returns:
            Lista di frasi
        """
        # Pattern per split su punti, punti esclamativi, interrogativi
        # Preserva abbreviazioni comuni
        sentences = re.split(r'(?<=[.!?])\s+(?=[A-Z])', text)
        
        # Filtra frasi troppo corte o vuote
        return [s.strip() for s in sentences if len(s.strip()) > 10]
    
    def _deduplicate_sentences(
        self,
        sentences: List[Tuple[str, float]],
        similarity_threshold: float = 0.7
    ) -> List[Tuple[str, float]]:
        """
        Rimuove frasi duplicate o molto simili.
        
        Args:
            sentences: Lista di (frase, score)
            similarity_threshold: Soglia di similarità per considerare duplicate
            
        Returns:
            Lista deduplicate di (frase, score)
        """
        if not sentences:
            return []
        
        unique: List[Tuple[str, float]] = []
        
        for sentence, score in sentences:
            # Controlla similarità con frasi già selezionate
            is_duplicate = False
            s_words = set(sentence.lower().split())
            
            for existing, _ in unique:
                e_words = set(existing.lower().split())
                
                # Calcola Jaccard similarity
                if len(s_words) > 0 and len(e_words) > 0:
                    intersection = len(s_words & e_words)
                    union = len(s_words | e_words)
                    similarity = intersection / union if union > 0 else 0.0
                    
                    if similarity >= similarity_threshold:
                        is_duplicate = True
                        break
            
            if not is_duplicate:
                unique.append((sentence, score))
        
        return unique
    
    def extract_key_sentences(
        self,
        text: str,
        query: str = "",
        top_n: int = 5
    ) -> List[str]:
        """
        Estrae le frasi più importanti da un testo.
        
        Args:
            text: Testo da sintetizzare
            query: Query originale (opzionale, per rilevanza)
            top_n: Numero di frasi da estrarre
            
        Returns:
            Lista delle frasi chiave
        """
        if not text or not text.strip():
            return []
        
        # Split in frasi
        sentences = self._split_sentences(text)
        if not sentences:
            return []
        
        # Estrai keywords dal testo e dalla query
        keywords = self._extract_keywords(text, top_n=15)
        if query:
            query_keywords = self._extract_keywords(query, top_n=5)
            # Aggiungi keywords della query con peso maggiore
            keywords = query_keywords + keywords
        
        # Score ogni frase
        scored_sentences: List[Tuple[str, float]] = []
        for i, sentence in enumerate(sentences):
            score = self._score_sentence(sentence, keywords, i, len(sentences))
            scored_sentences.append((sentence, score))
        
        # Ordina per score
        scored_sentences.sort(key=lambda x: x[1], reverse=True)
        
        # Deduplica
        unique_sentences = self._deduplicate_sentences(scored_sentences)
        
        # Ritorna top N
        return [s for s, _ in unique_sentences[:top_n]]
    
    def synthesize_multi_source(
        self,
        sources: List[Dict[str, Any]],
        query: str = "",
        max_key_points: int = 6
    ) -> SynthesisResult:
        """
        Sintetizza contenuti da multiple fonti.
        
        Args:
            sources: Lista di dict con keys: url, title, text
            query: Query originale
            max_key_points: Numero massimo di punti chiave
            
        Returns:
            SynthesisResult con sintesi e punti chiave
        """
        if not sources:
            return SynthesisResult(
                summary="Nessuna fonte disponibile.",
                key_points=[],
                sources=[],
                confidence=0.0
            )
        
        # Raccogli tutte le frasi chiave da tutte le fonti
        all_key_sentences: List[Tuple[str, float, int]] = []  # (sentence, score, source_idx)
        
        for idx, source in enumerate(sources):
            text = source.get("text", "")
            if not text:
                continue
            
            # Estrai frasi chiave
            key_sentences = self.extract_key_sentences(
                text,
                query=query,
                top_n=max_key_points
            )
            
            # Aggiungi con score e source index
            for i, sentence in enumerate(key_sentences):
                # Score decrescente per posizione
                position_score = 1.0 - (i / max(1, len(key_sentences)))
                all_key_sentences.append((sentence, position_score, idx))
        
        if not all_key_sentences:
            return SynthesisResult(
                summary="Impossibile estrarre informazioni dalle fonti.",
                key_points=[],
                sources=sources,
                confidence=0.0
            )
        
        # Deduplica e ordina per score
        unique_sentences = []
        seen_sentences: Set[str] = set()
        
        # Ordina per score
        all_key_sentences.sort(key=lambda x: x[1], reverse=True)
        
        for sentence, score, source_idx in all_key_sentences:
            # Check duplicazione semplice
            s_lower = sentence.lower()
            if s_lower not in seen_sentences:
                unique_sentences.append((sentence, score, source_idx))
                seen_sentences.add(s_lower)
            
            if len(unique_sentences) >= max_key_points:
                break
        
        # Crea key points
        key_points = [s for s, _, _ in unique_sentences]
        
        # Crea summary (prime 2-3 frasi)
        summary_sentences = key_points[:3]
        summary = " ".join(summary_sentences)
        
        # Calcola confidence
        confidence = min(1.0, len(key_points) / max(1, max_key_points))
        
        # Filtra sources per includere solo quelle usate
        used_source_indices = set(idx for _, _, idx in unique_sentences)
        used_sources = [
            {
                "url": sources[i].get("url", ""),
                "title": sources[i].get("title", ""),
            }
            for i in used_source_indices
            if i < len(sources)
        ]
        
        return SynthesisResult(
            summary=summary,
            key_points=key_points,
            sources=used_sources,
            confidence=confidence
        )


# Singleton instance
_synthesizer_instance: SmartSynthesizer | None = None


def get_smart_synthesizer() -> SmartSynthesizer:
    """
    Ottiene l'istanza singleton del synthesizer.
    
    Returns:
        SmartSynthesizer instance
    """
    global _synthesizer_instance
    if _synthesizer_instance is None:
        _synthesizer_instance = SmartSynthesizer()
    return _synthesizer_instance


def synthesize_content(
    sources: List[Dict[str, Any]],
    query: str = "",
    max_key_points: int = 6
) -> Dict[str, Any]:
    """
    Utility function per sintetizzare contenuti.
    
    Args:
        sources: Lista di fonti con text
        query: Query originale
        max_key_points: Numero massimo di punti chiave
        
    Returns:
        Dict con summary, key_points, sources, confidence
    """
    synthesizer = get_smart_synthesizer()
    result = synthesizer.synthesize_multi_source(sources, query, max_key_points)
    
    return {
        "summary": result.summary,
        "key_points": result.key_points,
        "sources": result.sources,
        "confidence": result.confidence,
    }
