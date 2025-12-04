#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/text_preprocessing.py — Text Preprocessing Module

Centralizes text normalization and pre-processing for user queries.
Provides clean text, language hints, and multi-question detection.
"""

import re
import unicodedata
from typing import Dict, Optional, Any

# Italian stopwords (subset for quick detection)
IT_STOPWORDS = {
    "il", "lo", "la", "i", "gli", "le", "un", "uno", "una",
    "di", "da", "del", "della", "dei", "degli", "delle",
    "che", "non", "mi", "ti", "si", "ci", "vi", "ne",
    "per", "con", "su", "in", "a", "sono", "è", "sei",
    "come", "cosa", "quando", "dove", "perché", "chi"
}

# English stopwords (subset for quick detection)
EN_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "in", "on", "at",
    "to", "for", "of", "with", "by", "from", "up", "down",
    "is", "are", "was", "were", "be", "been", "being",
    "what", "when", "where", "why", "how", "who"
}


def preprocess_user_query(raw_text: str) -> Dict[str, Any]:
    """
    Normalizza la query utente e fornisce info utili alla pipeline.
    
    Args:
        raw_text: Testo grezzo dell'utente
        
    Returns:
        Dict con:
        - clean_text: str        # testo normalizzato
        - lower_text: str        # versione lower-case
        - has_multiple_questions: bool
        - language_hint: Optional[str]  # "it", "en", None
    """
    if not raw_text:
        return {
            "clean_text": "",
            "lower_text": "",
            "has_multiple_questions": False,
            "language_hint": None,
        }
    
    # 1. Rimuovi caratteri di controllo e zero-width
    text = raw_text
    # Remove zero-width characters
    text = re.sub(r'[\u200b-\u200f\u202a-\u202e\ufeff]', '', text)
    # Remove other control characters except newlines and tabs
    text = ''.join(ch for ch in text if ch == '\n' or ch == '\t' or not unicodedata.category(ch).startswith('C'))
    
    # 2. Normalizza whitespace (riduci spazi multipli, strip)
    text = re.sub(r'\s+', ' ', text).strip()
    
    # 3. Lower-case version (preserva accenti)
    lower_text = text.lower()
    
    # 4. Detect multiple questions
    # Count question marks and strong separators
    question_marks = text.count('?')
    # Also check for multiple sentences with strong separators
    sentences = re.split(r'[.!?]+', text)
    # Filter out empty strings
    sentences = [s.strip() for s in sentences if s.strip()]
    
    has_multiple_questions = question_marks > 1 or len(sentences) > 2
    
    # 5. Language hint (simple heuristic)
    language_hint = _detect_language_simple(lower_text)
    
    return {
        "clean_text": text,
        "lower_text": lower_text,
        "has_multiple_questions": has_multiple_questions,
        "language_hint": language_hint,
    }


def _detect_language_simple(text: str) -> Optional[str]:
    """
    Semplice rilevamento lingua basato su stopwords prevalenti.
    
    Args:
        text: Testo in lower-case
        
    Returns:
        "it", "en", o None se non chiaro
    """
    if not text or len(text) < 5:
        return None
    
    # Tokenize roughly (remove punctuation)
    words = re.findall(r'\b\w+\b', text.lower())
    
    if not words:
        return None
    
    # Count stopwords matches
    it_count = sum(1 for w in words if w in IT_STOPWORDS)
    en_count = sum(1 for w in words if w in EN_STOPWORDS)
    
    # Need at least 1 stopword to make a guess (relaxed from 2)
    if it_count < 1 and en_count < 1:
        return None
    
    # Return language with most stopword matches
    if it_count > en_count:
        return "it"
    elif en_count > it_count:
        return "en"
    
    # Tie or unclear
    return None
