#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/italian_nlp.py — Italian NLP Utilities for QuantumDev

Features:
- Common Italian grammar error detection and correction
- Italian-specific tokenization helpers
- Intent keyword detection for Italian queries
- Italian-aware text summarization

Author: Matteo (QuantumDev)
Version: 1.0.0
"""

import re
import logging
from typing import Dict, List, Optional

log = logging.getLogger(__name__)

# === Grammar Correction Patterns ===

# Pattern replacements for common Italian grammar errors
GRAMMAR_FIXES = [
    # qual'è → qual è (no apostrophe)
    (r"\bqual'è\b", "qual è"),
    (r"\bQual'è\b", "Qual è"),
    (r"\bQual'È\b", "Qual È"),
    
    # un'altro/un'altra → un altro/un altra (no apostrophe before vowel for masculine)
    (r"\bun'altro\b", "un altro"),
    (r"\bUn'altro\b", "Un altro"),
    (r"\bun'Altri\b", "un altri"),
    
    # pò → po' (correct apostrophe)
    (r"\bpò\b", "po'"),
    (r"\bPò\b", "Po'"),
    
    # perchè → perché (accent correction)
    (r"\bperchè\b", "perché"),
    (r"\bPerchè\b", "Perché"),
    (r"\bpoichè\b", "poiché"),
    (r"\bPoichè\b", "Poiché"),
    
    # sè → sé (correct accent for reflexive pronoun)
    (r"\bsè\b", "sé"),
    (r"\bSè\b", "Sé"),
    
    # da → dà (when it's the verb "dare" - context-aware is complex, but we can catch some patterns)
    (r"\b(lui|lei|egli|ella)\s+da\s+(a|ad|al|alla)\b", r"\1 dà \2"),
    
    # è vs e (basic context detection: è before/after nouns/adjectives, e as conjunction)
    # This is complex and requires context - leaving basic patterns
    (r"\be\s+(molto|tanto|così|veramente|davvero)\b", r"è \1"),  # e molto → è molto
    
    # Multiple spaces to single space
    (r"\s{2,}", " "),
]


def fix_italian_grammar(text: str) -> str:
    """
    Correct common Italian grammar errors.
    
    Patterns fixed:
    - qual'è → qual è
    - un'altro → un altro
    - pò → po'
    - perchè → perché
    - sè → sé
    - Multiple spaces to single space
    
    Args:
        text: Input text to correct
        
    Returns:
        Text with grammar errors corrected
    """
    if not text or not isinstance(text, str):
        return text
    
    corrected = text
    
    # Apply all grammar fixes
    for pattern, replacement in GRAMMAR_FIXES:
        corrected = re.sub(pattern, replacement, corrected, flags=re.IGNORECASE if pattern.lower() == pattern else 0)
    
    return corrected.strip()


# === Italian Intent Keywords ===

ITALIAN_INTENT_KEYWORDS = {
    "search": [
        "cerca", "cercare", "trova", "trovare", "ricerca", "ricercare",
        "dimmi", "mostrami", "fammi vedere", "info su", "informazioni",
        "cos'è", "cosa è", "chi è", "dove", "quando", "come", "perché"
    ],
    "weather": [
        "meteo", "tempo", "temperatura", "previsioni", "piove", "sole",
        "clima", "freddo", "caldo", "che tempo fa"
    ],
    "news": [
        "notizie", "news", "ultime notizie", "aggiornamenti", "cosa succede",
        "novità", "attualità", "cronaca"
    ],
    "calculation": [
        "calcola", "calcolare", "quanto fa", "somma", "risultato",
        "dividere", "moltiplicare", "sottrarre", "matematica"
    ],
    "reminder": [
        "ricordami", "ricorda", "promemoria", "appuntamento", "avviso",
        "non dimenticare", "segna", "nota"
    ],
    "memory": [
        "ricordati", "memorizza", "salva", "tieni a mente",
        "da ora in poi", "ricorda che"
    ],
    "question": [
        "domanda", "chiedo", "mi chiedo", "vorrei sapere", "mi piacerebbe sapere",
        "puoi dirmi", "potresti dirmi", "spiegami", "spiegare"
    ],
    "command": [
        "fai", "fare", "esegui", "eseguire", "avvia", "avviare",
        "apri", "aprire", "chiudi", "chiudere", "crea", "creare"
    ],
    "greeting": [
        "ciao", "salve", "buongiorno", "buonasera", "buonanotte",
        "hey", "ehi", "hola"
    ],
}


def detect_italian_intent_keywords(query: str) -> Dict[str, float]:
    """
    Detect Italian intent keywords and return confidence scores.
    
    Args:
        query: User query text
        
    Returns:
        Dict mapping intent names to confidence scores (0-1)
    """
    if not query or not isinstance(query, str):
        return {}
    
    query_lower = query.lower()
    intent_scores: Dict[str, float] = {}
    
    for intent, keywords in ITALIAN_INTENT_KEYWORDS.items():
        matches = 0
        for keyword in keywords:
            if keyword in query_lower:
                matches += 1
        
        if matches > 0:
            # Normalize score: more matches = higher confidence
            # Cap at 1.0
            score = min(matches / len(keywords) * 5, 1.0)
            intent_scores[intent] = score
    
    return intent_scores


# === Italian-Aware Summarization ===

def italian_aware_summarization(text: str, max_words: int = 100) -> str:
    """
    Summarize text while respecting Italian language structure.
    
    This is a simple extractive summarization that:
    1. Splits text into sentences
    2. Selects the most important sentences
    3. Respects Italian punctuation and structure
    
    Args:
        text: Text to summarize
        max_words: Maximum number of words in summary
        
    Returns:
        Summarized text
    """
    if not text or not isinstance(text, str):
        return ""
    
    # Split into sentences (Italian sentence endings)
    sentences = re.split(r'[.!?]+\s+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    if not sentences:
        return ""
    
    # If already short enough, return as is
    word_count = len(text.split())
    if word_count <= max_words:
        return text
    
    # Simple heuristic: take first and last sentences, then fill from middle
    summary_sentences = []
    words_used = 0
    
    # Always include first sentence (usually contains main topic)
    if sentences:
        first_sent = sentences[0]
        first_words = len(first_sent.split())
        if words_used + first_words <= max_words:
            summary_sentences.append(first_sent)
            words_used += first_words
    
    # Try to include last sentence (often contains conclusion)
    if len(sentences) > 1:
        last_sent = sentences[-1]
        last_words = len(last_sent.split())
        if words_used + last_words <= max_words:
            summary_sentences.append(last_sent)
            words_used += last_words
    
    # Fill with middle sentences based on length (prefer shorter, more concise ones)
    middle_sentences = sentences[1:-1] if len(sentences) > 2 else []
    middle_sentences.sort(key=lambda s: len(s.split()))  # Sort by word count
    
    for sent in middle_sentences:
        sent_words = len(sent.split())
        if words_used + sent_words <= max_words:
            summary_sentences.append(sent)
            words_used += sent_words
        else:
            break
    
    # Reconstruct summary in original order
    summary = ". ".join(summary_sentences)
    if summary and not summary.endswith(('.', '!', '?')):
        summary += "."
    
    return summary


# === Italian Text Preprocessing ===

def normalize_italian_text(text: str) -> str:
    """
    Normalize Italian text for better processing.
    
    - Fixes grammar errors
    - Normalizes whitespace
    - Removes extra punctuation
    
    Args:
        text: Input text
        
    Returns:
        Normalized text
    """
    if not text or not isinstance(text, str):
        return text
    
    # Fix grammar
    normalized = fix_italian_grammar(text)
    
    # Normalize quotes
    normalized = re.sub(r'["""]', '"', normalized)
    normalized = re.sub(r"[''']", "'", normalized)
    
    # Remove multiple punctuation (e.g., "???" → "?")
    normalized = re.sub(r'([.!?])\1+', r'\1', normalized)
    
    # Normalize whitespace around punctuation
    normalized = re.sub(r'\s+([.!?,;:])', r'\1', normalized)
    normalized = re.sub(r'([.!?])\s*([A-ZÀÈÉÌÒÙ])', r'\1 \2', normalized)
    
    return normalized.strip()


# === Export ===

__all__ = [
    "fix_italian_grammar",
    "detect_italian_intent_keywords",
    "italian_aware_summarization",
    "normalize_italian_text",
]


# === Test ===
if __name__ == "__main__":
    print("🧪 Testing Italian NLP Utilities")
    print("=" * 60)
    
    # Test grammar fixes
    test_texts = [
        "qual'è il tuo nome?",
        "Voglio un'altro caffè",
        "Non ne posso pò",
        "perchè non funziona?",
        "Fallo da solo, se vuoi",
    ]
    
    print("\n📝 Grammar Fixes:")
    for text in test_texts:
        fixed = fix_italian_grammar(text)
        if fixed != text:
            print(f"  ✓ '{text}' → '{fixed}'")
        else:
            print(f"  - '{text}' (no changes)")
    
    # Test intent detection
    print("\n🎯 Intent Detection:")
    test_queries = [
        "Cerca informazioni su Python",
        "Che tempo fa domani?",
        "Ultime notizie di oggi",
        "Ciao, come stai?",
    ]
    
    for query in test_queries:
        intents = detect_italian_intent_keywords(query)
        print(f"  '{query}'")
        for intent, score in sorted(intents.items(), key=lambda x: x[1], reverse=True):
            print(f"    → {intent}: {score:.2f}")
    
    # Test summarization
    print("\n✂️  Summarization:")
    long_text = (
        "QuantumDev è un sistema AI avanzato per assistente personale. "
        "Utilizza Python e FastAPI per il backend. "
        "Include funzionalità di memoria conversazionale persistente. "
        "Il sistema supporta web search multi-engine. "
        "L'interfaccia principale è tramite Telegram bot. "
        "Supporta reasoning traces e artifacts per debugging. "
        "Il context window è di 65K tokens per massima capacità."
    )
    
    summary = italian_aware_summarization(long_text, max_words=30)
    print(f"  Original ({len(long_text.split())} words):")
    print(f"    {long_text}")
    print(f"  Summary ({len(summary.split())} words):")
    print(f"    {summary}")
    
    print("\n✅ All tests completed!")
