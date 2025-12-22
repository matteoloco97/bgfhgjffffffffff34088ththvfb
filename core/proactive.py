#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/proactive.py — Proactive Suggestions for QuantumDev Max

Features:
- LLM-driven suggestion generation
- Context-aware recommendations
- Next-action predictions

Author: Matteo (QuantumDev)
Version: 2.0.0
"""

from __future__ import annotations

import os
import logging
from typing import List, Optional, Any, Callable

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === ENV Configuration ===
MAX_SUGGESTIONS = int(os.getenv("MAX_PROACTIVE_SUGGESTIONS", "3"))


async def generate_suggestions(
    session: Any,
    query: str,
    llm_func: Callable
) -> List[str]:
    """
    Generate proactive suggestions based on user query.
    
    Uses the LLM to predict what the user might want to do next.
    
    Args:
        session: Current conversation session
        query: User's current query
        llm_func: Async LLM function to call
        
    Returns:
        List of suggestion strings
    """
    if not llm_func:
        log.warning("No LLM function provided for suggestions")
        return []
    
    try:
        # Build prompt for suggestions
        prompt = (
            f"L'utente ha appena chiesto: \"{query}\"\n\n"
            "Quali ulteriori azioni o ricerche sarebbero utili all'utente dopo questa richiesta? "
            f"Rispondi con un elenco di {MAX_SUGGESTIONS} suggerimenti pratici e specifici.\n\n"
            "Formato:\n"
            "1. [primo suggerimento]\n"
            "2. [secondo suggerimento]\n"
            "3. [terzo suggerimento]"
        )
        
        system = (
            "Sei un assistente proattivo che anticipa i bisogni dell'utente. "
            "Genera suggerimenti utili, specifici e actionable basati sul contesto della conversazione."
        )
        
        # Call LLM
        response = await llm_func(prompt, system)
        
        if not response:
            return []
        
        # Parse suggestions from response
        suggestions = []
        lines = response.strip().split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Remove numbering (1., 2., -, *, etc.)
            import re
            cleaned = re.sub(r'^[\d\.\-\*\•]\s*', '', line)
            
            if cleaned and len(cleaned) > 5:  # Minimum length check
                suggestions.append(cleaned)
        
        # Limit to MAX_SUGGESTIONS
        suggestions = suggestions[:MAX_SUGGESTIONS]
        
        log.info(f"Generated {len(suggestions)} proactive suggestions")
        return suggestions
        
    except Exception as e:
        log.error(f"Failed to generate suggestions: {e}")
        return []


# === Test ===
if __name__ == "__main__":
    import asyncio
    
    async def mock_llm(prompt: str, system: str) -> str:
        """Mock LLM for testing."""
        return (
            "1. Approfondire l'argomento con una ricerca più specifica\n"
            "2. Chiedere esempi pratici o casi d'uso\n"
            "3. Esplorare argomenti correlati"
        )
    
    async def test():
        suggestions = await generate_suggestions(
            None,
            "Cos'è il quantum computing?",
            mock_llm
        )
        print("Suggestions:", suggestions)
    
    asyncio.run(test())
