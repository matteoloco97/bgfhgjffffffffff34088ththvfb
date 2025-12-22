#!/usr/bin/env python3
# core/token_budget.py — Token budget utilities (ottimizzato)

import re
from typing import List

# Cache per evitare ricalcoli
_TOKEN_CACHE = {}
_CACHE_MAX_SIZE = 1000


def approx_tokens(text: str) -> int:
    """
    Stima veloce token count.
    
    Regola euristica ottimizzata:
    - Inglese/Italiano: ~4 char = 1 token
    - Aggiustamento per punteggiatura
    - Cache per testi identici
    """
    if not text:
        return 0
    
    # Cache check
    cache_key = hash(text) if len(text) < 500 else None
    if cache_key and cache_key in _TOKEN_CACHE:
        return _TOKEN_CACHE[cache_key]
    
    # Quick estimate
    char_count = len(text)
    
    # Penalità per codice (molti simboli)
    if text.count("{") + text.count("[") + text.count("(") > char_count * 0.05:
        tokens = int(char_count / 3)  # Codice è più denso
    else:
        tokens = int(char_count / 4)
    
    # Cache se non troppo grande
    if cache_key and len(_TOKEN_CACHE) < _CACHE_MAX_SIZE:
        _TOKEN_CACHE[cache_key] = tokens
    
    return tokens


def trim_to_tokens(text: str, max_tokens: int) -> str:
    """
    Trim intelligente mantenendo frasi intere.
    
    Strategia:
    1. Stima char limit da token limit
    2. Taglia a frase intera più vicina
    3. Mantiene paragrafi se possibile
    """
    if not text or max_tokens <= 0:
        return ""
    
    current_tokens = approx_tokens(text)
    if current_tokens <= max_tokens:
        return text
    
    # Stima char limit
    target_chars = int(max_tokens * 4)
    
    # Se molto più lungo, taglia grossolanamente prima
    if len(text) > target_chars * 2:
        text = text[:target_chars * 2]
    
    # Split in frasi
    sentences = re.split(r'([.!?]+\s+)', text)
    
    # Ricostruisci fino a budget
    result = []
    char_count = 0
    
    for i in range(0, len(sentences), 2):
        sentence = sentences[i]
        separator = sentences[i + 1] if i + 1 < len(sentences) else ""
        
        chunk = sentence + separator
        chunk_len = len(chunk)
        
        if char_count + chunk_len > target_chars and result:
            # Abbiamo già qualcosa, stop qui
            break
        
        result.append(chunk)
        char_count += chunk_len
    
    trimmed = "".join(result).strip()
    
    # Fallback se trim troppo aggressivo
    if len(trimmed) < 100 and len(text) > 100:
        return text[:target_chars].rsplit(" ", 1)[0] + "..."
    
    return trimmed


def smart_trim_extracts(
    extracts: List[dict],
    total_budget: int,
    strategy: str = "proportional"
) -> List[dict]:
    """
    Trim intelligente di più estratti rispettando budget totale.
    
    Strategies:
    - "proportional": Budget proporzionale a qualità/position
    - "equal": Budget uguale per tutti
    - "top_heavy": Più budget ai top results
    """
    if not extracts or total_budget <= 0:
        return extracts
    
    n = len(extracts)
    
    if strategy == "equal":
        budget_each = total_budget // n
        budgets = [budget_each] * n
    
    elif strategy == "top_heavy":
        # 40% top, 30% secondo, 20% terzo, 10% resto
        if n == 1:
            budgets = [total_budget]
        elif n == 2:
            budgets = [int(total_budget * 0.6), int(total_budget * 0.4)]
        elif n == 3:
            budgets = [
                int(total_budget * 0.4),
                int(total_budget * 0.3),
                int(total_budget * 0.3),
            ]
        else:
            budgets = [
                int(total_budget * 0.4),
                int(total_budget * 0.3),
                int(total_budget * 0.2),
            ] + [int(total_budget * 0.1 / (n - 3))] * (n - 3)
    
    else:  # proportional (default)
        # Considera rerank_score se disponibile
        scores = [e.get("rerank_score", 0.5) for e in extracts]
        total_score = sum(scores)
        if total_score > 0:
            budgets = [int(total_budget * (s / total_score)) for s in scores]
        else:
            # Fallback equal
            budget_each = total_budget // n
            budgets = [budget_each] * n
    
    # Apply trim
    trimmed = []
    for extract, budget in zip(extracts, budgets):
        text = extract.get("text", "")
        trimmed_text = trim_to_tokens(text, budget)
        
        new_extract = dict(extract)
        new_extract["text"] = trimmed_text
        new_extract["budget_allocated"] = budget
        new_extract["budget_used"] = approx_tokens(trimmed_text)
        trimmed.append(new_extract)
    
    return trimmed


def clear_token_cache():
    """Svuota cache token (utile per testing)"""
    _TOKEN_CACHE.clear()
