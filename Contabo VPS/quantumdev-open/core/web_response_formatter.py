#!/usr/bin/env python3
"""
core/web_response_formatter.py
===============================

Ultra-concise web response formatter that generates short, direct answers
from web search extracts without verbose preambles or source citations.

PROBLEMA 2 FIX: Risposte web troppo verbose (150+ parole)
- Template prompt ultra-conciso (max 50 parole, zero preamble)
- Post-processing per rimuovere frasi tipo "basandomi sulle fonti"
- Hard limit: 120 tokens max
"""

from __future__ import annotations

import logging
import re
from typing import List, Dict, Any, Callable, Awaitable, Optional

# Setup logging
log = logging.getLogger(__name__)

# Pre-compile regex patterns for performance (module level)
_HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
_HTML_ENTITY_PATTERN = re.compile(r'&[a-zA-Z]+;|&#\d+;')
_DUPLICATE_WHITESPACE = re.compile(r'\s+')
_DUPLICATE_SENTENCES = re.compile(r'(\b.{20,}\b).*?\1', re.IGNORECASE)
_VERBOSE_PHRASES_COMPILED = None  # Will be compiled on first use

# Hard limit on response tokens
MAX_RESPONSE_TOKENS = 120
MAX_RESPONSE_WORDS = 50

# Phrases to remove from responses (verbose preambles)
VERBOSE_PHRASES = [
    r"basandomi sulle fonti",
    r"secondo le fonti",
    r"in base ai documenti",
    r"dalle informazioni disponibili",
    r"stando alle informazioni",
    r"dalle fonti fornite",
    r"secondo quanto riportato",
    r"based on the sources",
    r"according to the sources",
    r"from the information provided",
    r"based on the documents",
]


def _get_verbose_phrases_compiled():
    """Lazy compile verbose phrases patterns (singleton pattern)."""
    global _VERBOSE_PHRASES_COMPILED
    if _VERBOSE_PHRASES_COMPILED is None:
        _VERBOSE_PHRASES_COMPILED = [
            re.compile(pattern, re.IGNORECASE) for pattern in VERBOSE_PHRASES
        ]
    return _VERBOSE_PHRASES_COMPILED


def _clean_extract(text: str) -> str:
    """Pulizia veloce HTML/duplicati usando pattern pre-compilati.
    
    Parameters
    ----------
    text : str
        Testo estratto da pulire.
    
    Returns
    -------
    str
        Testo pulito senza HTML, entità, duplicati.
    """
    if not text:
        return ""
    
    # Remove HTML tags
    cleaned = _HTML_TAG_PATTERN.sub('', text)
    
    # Remove HTML entities
    cleaned = _HTML_ENTITY_PATTERN.sub(' ', cleaned)
    
    # Normalize whitespace
    cleaned = _DUPLICATE_WHITESPACE.sub(' ', cleaned)
    
    # Remove obvious duplicates (same sentence repeated)
    cleaned = _DUPLICATE_SENTENCES.sub(r'\1', cleaned)
    
    return cleaned.strip()


def _remove_verbose_phrases(text: str) -> str:
    """Remove verbose preamble phrases from the response text.
    
    Uses pre-compiled regex patterns for better performance.
    
    Parameters
    ----------
    text : str
        The response text to clean.
    
    Returns
    -------
    str
        Cleaned text without verbose phrases.
    """
    if not text:
        return ""
    
    cleaned = text
    compiled_patterns = _get_verbose_phrases_compiled()
    
    for pattern in compiled_patterns:
        cleaned = pattern.sub("", cleaned)
    
    # Clean up any resulting double spaces or leading/trailing commas
    cleaned = _DUPLICATE_WHITESPACE.sub(' ', cleaned)
    cleaned = re.sub(r'^\s*,\s*', '', cleaned)
    cleaned = re.sub(r'\s*,\s*$', '', cleaned)
    
    return cleaned.strip()


def _enforce_token_limit(text: str, max_tokens: int = MAX_RESPONSE_TOKENS) -> str:
    """Enforce hard token limit by truncating text.
    
    Uses simple approximation: 1 token ≈ 4 characters.
    
    Parameters
    ----------
    text : str
        The text to limit.
    max_tokens : int
        Maximum number of tokens allowed.
    
    Returns
    -------
    str
        Truncated text if necessary.
    """
    if not text:
        return ""
    
    # Approximate: 1 token ≈ 4 characters
    max_chars = max_tokens * 4
    
    if len(text) <= max_chars:
        return text
    
    # Truncate at sentence boundary if possible
    truncated = text[:max_chars]
    
    # Try to find last sentence ending
    last_period = max(
        truncated.rfind('.'),
        truncated.rfind('!'),
        truncated.rfind('?')
    )
    
    if last_period > max_chars * 0.7:  # At least 70% of limit
        return truncated[:last_period + 1].strip()
    
    # Otherwise just truncate with ellipsis
    return truncated.rsplit(' ', 1)[0].strip() + '...'


def _count_words(text: str) -> int:
    """Count words in text (simple whitespace-based).
    
    Parameters
    ----------
    text : str
        Text to count words in.
    
    Returns
    -------
    int
        Number of words.
    """
    if not text:
        return 0
    return len(text.split())


def _approx_tokens(text: str) -> int:
    """Fast token approximation (1 token ≈ 4 characters).
    
    Parameters
    ----------
    text : str
        Text to estimate tokens for.
    
    Returns
    -------
    int
        Approximate number of tokens.
    """
    if not text:
        return 0
    return len(text) // 4


def _extract_keywords(query: str, top_n: int = 5) -> List[str]:
    """Extract top keywords from query for relevance scoring.
    
    Parameters
    ----------
    query : str
        User query.
    top_n : int, optional
        Number of top keywords to extract.
    
    Returns
    -------
    List[str]
        List of keywords (lowercased, no stopwords).
    """
    # Simple keyword extraction (remove common stopwords)
    stopwords = {
        'il', 'lo', 'la', 'i', 'gli', 'le', 'di', 'da', 'a', 'in', 'su', 'per',
        'con', 'tra', 'fra', 'che', 'e', 'o', 'ma', 'come', 'quando', 'dove',
        'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'of', 'and', 'or',
        'what', 'when', 'where', 'how', 'why', 'is', 'are', 'was', 'were',
    }
    
    words = query.lower().split()
    keywords = [w for w in words if len(w) > 2 and w not in stopwords]
    
    # Return top_n or all if fewer
    return keywords[:top_n]


def _score_extract_relevance(extract_text: str, keywords: List[str]) -> float:
    """Score extract relevance based on keyword presence.
    
    Parameters
    ----------
    extract_text : str
        Extract text to score.
    keywords : List[str]
        Keywords from query.
    
    Returns
    -------
    float
        Relevance score (0.0 to 1.0).
    """
    if not keywords or not extract_text:
        return 0.5  # Neutral score
    
    text_lower = extract_text.lower()
    matches = sum(1 for kw in keywords if kw in text_lower)
    
    return min(1.0, matches / len(keywords))


def smart_trim_extracts(
    extracts: List[Dict[str, Any]], 
    query: str,
    max_sources: int = 5,
    max_chars_per_source: int = 200,
    max_total_tokens: int = 400
) -> List[Dict[str, Any]]:
    """Trim intelligente estratti mantenendo info chiave.
    
    Strategia:
    1. Limita a max_sources fonti
    2. Calcola token per estratto
    3. Prioritizza estratti con keywords dalla query
    4. Tronca intelligentemente mantenendo frasi complete
    5. Bilancia tra quantità fonti e profondità per fonte
    
    Parameters
    ----------
    extracts : List[Dict[str, Any]]
        Lista estratti con keys: url, title, text.
    query : str
        Query utente per keyword extraction.
    max_sources : int, optional
        Numero massimo di fonti da mantenere.
    max_chars_per_source : int, optional
        Massimo caratteri per fonte.
    max_total_tokens : int, optional
        Budget totale token per tutti gli estratti.
    
    Returns
    -------
    List[Dict[str, Any]]
        Lista di estratti trimmed, max max_sources fonti.
    
    Examples
    --------
    >>> extracts = [
    ...     {"url": "...", "title": "Bitcoin", "text": "Bitcoin è..."},
    ...     {"url": "...", "title": "Crypto", "text": "Le crypto..."}
    ... ]
    >>> trimmed = smart_trim_extracts(extracts, "prezzo bitcoin")
    >>> len(trimmed) <= 5
    True
    """
    if not extracts:
        return []
    
    # 1. Limit to max_sources
    limited = extracts[:max_sources]
    
    # 2. Extract keywords from query
    keywords = _extract_keywords(query)
    
    # 3. Score and sort by relevance
    scored_extracts = []
    for ext in limited:
        text = ext.get('text', '')
        score = _score_extract_relevance(text, keywords)
        scored_extracts.append((score, ext))
    
    # Sort by score descending
    scored_extracts.sort(key=lambda x: x[0], reverse=True)
    
    # 4. Clean and trim each extract
    trimmed_extracts = []
    total_tokens_used = 0
    
    for score, ext in scored_extracts:
        text = ext.get('text', '')
        
        # Clean HTML and duplicates
        cleaned_text = _clean_extract(text)
        
        # Trim to max chars, preserving sentence boundaries
        if len(cleaned_text) > max_chars_per_source:
            # Try to cut at sentence boundary
            truncated = cleaned_text[:max_chars_per_source]
            last_period = max(
                truncated.rfind('.'),
                truncated.rfind('!'),
                truncated.rfind('?')
            )
            
            if last_period > max_chars_per_source * 0.6:  # At least 60% of limit
                cleaned_text = truncated[:last_period + 1].strip()
            else:
                # Cut at word boundary
                cleaned_text = truncated.rsplit(' ', 1)[0].strip() + '...'
        
        # Calculate tokens
        tokens = _approx_tokens(cleaned_text)
        
        # Check budget
        if total_tokens_used + tokens > max_total_tokens and trimmed_extracts:
            # If we already have some extracts, stop here
            break
        
        total_tokens_used += tokens
        
        # Create trimmed extract
        trimmed_ext = {
            'url': ext.get('url', ''),
            'title': ext.get('title', ''),
            'text': cleaned_text,
            'tokens': tokens,
            'relevance_score': score,
        }
        
        trimmed_extracts.append(trimmed_ext)
    
    log.info(
        f"Smart trim: {len(extracts)} → {len(trimmed_extracts)} sources, "
        f"{total_tokens_used} tokens (budget: {max_total_tokens})"
    )
    
    return trimmed_extracts


def _build_concise_prompt(
    query: str,
    extracts: List[Dict[str, Any]],
) -> str:
    """Build ultra-concise synthesis prompt (max 50 words output).
    
    Uses smart trimming to optimize input for faster LLM processing.
    
    Parameters
    ----------
    query : str
        The user's original query.
    extracts : List[Dict[str, Any]]
        List of web page extracts with keys: url, title, text.
    
    Returns
    -------
    str
        The formatted prompt for LLM.
    """
    # Apply smart trimming BEFORE building prompt (reduces tokens)
    trimmed_extracts = smart_trim_extracts(
        extracts, 
        query, 
        max_sources=3,  # Max 3 sources for speed
        max_chars_per_source=200,  # 200 chars per source
        max_total_tokens=400  # Total budget for all extracts
    )
    
    # Build context from trimmed extracts
    context_parts: List[str] = []
    for i, extract in enumerate(trimmed_extracts, 1):
        title = extract.get('title', 'Untitled')
        text = extract.get('text', '')
        
        context_parts.append(f"[{i}] {title}: {text}")
    
    context = "\n".join(context_parts)
    
    # Ultra-concise prompt template
    prompt = f"""ESTRATTI WEB:
{context}

DOMANDA: {query}

RISPONDI IN MAX 2-3 FRASI DIRETTE (MAX 50 PAROLE):
- Vai dritto al punto, zero preamble
- NON dire "basandomi sulle fonti" o simili
- Fornisci solo i fatti essenziali
- Numeri, date e dettagli concreti quando presenti"""

    return prompt


async def format_web_response(
    query: str,
    extracts: List[Dict[str, Any]],
    llm_func: Callable[[str, str], Awaitable[str]],
    persona: str = "",
) -> str:
    """Format a concise web response from query and extracts.
    
    This is the main function for PROBLEMA 2 fix. It generates an
    ultra-concise answer (max 50 words, 120 tokens) without verbose
    preambles.
    
    Parameters
    ----------
    query : str
        The user's original query.
    extracts : List[Dict[str, Any]]
        List of web page extracts with keys: url, title, text.
    llm_func : Callable
        Async function to call LLM: llm_func(prompt, persona) -> response.
    persona : str, optional
        System persona/prompt for LLM context.
    
    Returns
    -------
    str
        Ultra-concise formatted response (max 120 tokens).
    
    Examples
    --------
    >>> # Example usage (pseudo-code)
    >>> extracts = [
    ...     {"url": "...", "title": "Bitcoin Price", "text": "Bitcoin is at $45000..."}
    ... ]
    >>> response = await format_web_response(
    ...     query="Prezzo Bitcoin",
    ...     extracts=extracts,
    ...     llm_func=my_llm_function,
    ...     persona="Sei un assistente conciso"
    ... )
    >>> len(response.split()) <= 50  # True
    """
    if not extracts:
        log.warning("No extracts provided for web response formatting")
        return "Nessuna informazione trovata."
    
    # Build concise prompt
    prompt = _build_concise_prompt(query, extracts)
    
    try:
        # Call LLM
        response = await llm_func(prompt, persona)
        
        if not response:
            log.warning("LLM returned empty response")
            return "Risposta non disponibile."
        
        # Post-processing: remove verbose phrases
        response = _remove_verbose_phrases(response)
        
        # Enforce token limit (hard limit: 120 tokens)
        response = _enforce_token_limit(response, MAX_RESPONSE_TOKENS)
        
        # Final word count check
        word_count = _count_words(response)
        if word_count > MAX_RESPONSE_WORDS * 1.5:  # Allow 50% overflow
            log.warning(
                f"Response still verbose ({word_count} words), "
                f"target was {MAX_RESPONSE_WORDS}"
            )
        
        log.info(
            f"Formatted web response: {word_count} words, "
            f"~{len(response) // 4} tokens"
        )
        
        return response
    
    except Exception as e:
        log.error(f"Error formatting web response: {e}")
        # Fallback: return first extract title + snippet
        first = extracts[0]
        fallback = f"{first.get('title', '')}: {first.get('text', '')[:100]}..."
        return _enforce_token_limit(fallback, MAX_RESPONSE_TOKENS)


# Legacy compatibility function (if needed)
def format_web_response_sync(
    query: str,
    extracts: List[Dict[str, Any]],
) -> str:
    """Synchronous fallback that just formats extracts without LLM.
    
    This is a simple fallback for cases where LLM is not available.
    Returns first extract with token limit.
    
    Parameters
    ----------
    query : str
        The user's original query (unused in this fallback).
    extracts : List[Dict[str, Any]]
        List of web page extracts.
    
    Returns
    -------
    str
        Simple formatted response from first extract.
    """
    if not extracts:
        return "Nessuna informazione trovata."
    
    first = extracts[0]
    text = first.get('text', '')
    
    # Take first paragraph or ~200 chars
    text_parts = text.split('\n\n')
    snippet = text_parts[0] if text_parts else text[:200]
    
    return _enforce_token_limit(snippet, MAX_RESPONSE_TOKENS)
