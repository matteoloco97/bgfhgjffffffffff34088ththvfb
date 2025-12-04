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


def _remove_verbose_phrases(text: str) -> str:
    """Remove verbose preamble phrases from the response text.
    
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
    for phrase_pattern in VERBOSE_PHRASES:
        cleaned = re.sub(phrase_pattern, "", cleaned, flags=re.IGNORECASE)
    
    # Clean up any resulting double spaces or leading/trailing commas
    cleaned = re.sub(r'\s+', ' ', cleaned)
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


def _build_concise_prompt(
    query: str,
    extracts: List[Dict[str, Any]],
) -> str:
    """Build ultra-concise synthesis prompt (max 50 words output).
    
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
    # Build context from extracts
    context_parts: List[str] = []
    for i, extract in enumerate(extracts[:3], 1):  # Max 3 sources
        title = extract.get('title', 'Untitled')
        text = extract.get('text', '')
        
        # Limit each extract to ~200 chars
        text_snippet = text[:200].strip()
        if len(text) > 200:
            text_snippet += '...'
        
        context_parts.append(f"[{i}] {title}: {text_snippet}")
    
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
