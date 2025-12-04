#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/memory_context_builder.py — Memory Context Builder

Constructs memory context from user profile and episodic memory
to inject into LLM prompts for personalized responses.
"""

import os
import re
import logging
from typing import Dict, List, Optional, Tuple

log = logging.getLogger(__name__)

# Import memory modules
try:
    from core.user_profile_memory import (
        query_user_profile,
        get_all_user_facts,
        USER_PROFILE_ENABLED,
    )
    PROFILE_AVAILABLE = True
except Exception as e:
    log.warning(f"User profile memory not available: {e}")
    PROFILE_AVAILABLE = False
    USER_PROFILE_ENABLED = False
    
    def query_user_profile(*args, **kwargs):
        return []
    
    def get_all_user_facts(*args, **kwargs):
        return []

try:
    from core.episodic_memory import (
        query_conversation_history,
        get_recent_conversation_summaries,
        EPISODIC_ENABLED,
    )
    EPISODIC_AVAILABLE = True
except Exception as e:
    log.warning(f"Episodic memory not available: {e}")
    EPISODIC_AVAILABLE = False
    EPISODIC_ENABLED = False
    
    def query_conversation_history(*args, **kwargs):
        return []
    
    def get_recent_conversation_summaries(*args, **kwargs):
        return []

try:
    from core.token_budget import approx_tokens, trim_to_tokens
except Exception:
    def approx_tokens(s: str) -> int:
        return len(s or "") // 4
    
    def trim_to_tokens(s: str, max_tokens: int) -> str:
        if not s or max_tokens <= 0:
            return ""
        max_chars = max_tokens * 4
        return s[:max_chars]


# Pattern per riconoscere domande su se stesso ("self-questions")
SELF_QUESTION_PATTERNS = [
    r"\b(io|me|mio|mia|miei|mie)\b",
    r"\b(chi\s+sono|cosa\s+sai\s+di\s+me|cosa\s+ti\s+ricordi)\b",
    r"\b(le\s+mie\s+|il\s+mio\s+|la\s+mia\s+)",
    r"\b(about\s+me|my\s+|mine|who\s+am\s+i)\b",
]


def is_self_question(query_lower: str) -> bool:
    """
    Rileva se una query contiene riferimenti all'utente stesso.
    
    Args:
        query_lower: Query in lowercase
        
    Returns:
        True se sembra una domanda su se stesso
    """
    if not query_lower:
        return False
    
    for pattern in SELF_QUESTION_PATTERNS:
        if re.search(pattern, query_lower, re.IGNORECASE):
            return True
    
    return False


def build_memory_context(
    user_id: str,
    query: str,
    query_lower: str,
    conversation_id: Optional[str] = None,
    profile_top_k: int = 5,
    episodic_top_k: int = 3,
    max_tokens: int = 800,
) -> Dict[str, any]:
    """
    Costruisce contesto memory da user profile e episodic memory.
    
    Args:
        user_id: ID utente
        query: Query originale
        query_lower: Query in lowercase (per pattern matching)
        conversation_id: ID conversazione (opzionale, per episodic memory)
        profile_top_k: Numero massimo di fatti profilo da recuperare
        episodic_top_k: Numero massimo di episodi da recuperare
        max_tokens: Budget massimo token per il contesto totale
        
    Returns:
        Dict con:
        - context_text: str (testo formattato da inserire nel prompt)
        - is_self_question: bool
        - profile_facts: List[Dict]
        - episodic_summaries: List[Dict]
        - total_tokens: int (stima)
    """
    result = {
        "context_text": "",
        "is_self_question": False,
        "profile_facts": [],
        "episodic_summaries": [],
        "total_tokens": 0,
    }
    
    # Check se è una self-question
    is_self_q = is_self_question(query_lower)
    result["is_self_question"] = is_self_q
    
    context_parts: List[str] = []
    
    # === USER PROFILE MEMORY ===
    if USER_PROFILE_ENABLED and PROFILE_AVAILABLE:
        try:
            # Se è self-question, recupera tutti i fatti principali
            if is_self_q:
                profile_facts = get_all_user_facts(user_id=user_id, limit=profile_top_k)
            else:
                # Altrimenti, recupera fatti rilevanti alla query
                profile_facts = query_user_profile(
                    user_id=user_id,
                    query_text=query,
                    top_k=profile_top_k,
                )
            
            if profile_facts:
                result["profile_facts"] = profile_facts
                
                # Format profile facts
                profile_lines = ["📌 Informazioni utente:"]
                for fact in profile_facts[:profile_top_k]:
                    text = fact.get("text", "")
                    if text:
                        profile_lines.append(f"  - {text}")
                
                profile_section = "\n".join(profile_lines)
                context_parts.append(profile_section)
                
                log.debug(f"User profile: {len(profile_facts)} facts retrieved")
        
        except Exception as e:
            log.warning(f"Failed to retrieve user profile: {e}")
    
    # === EPISODIC MEMORY ===
    if EPISODIC_ENABLED and EPISODIC_AVAILABLE and conversation_id:
        try:
            # Recupera episodi rilevanti alla query
            episodic_summaries = query_conversation_history(
                conversation_id=conversation_id,
                query_text=query,
                top_k=episodic_top_k,
            )
            
            if episodic_summaries:
                result["episodic_summaries"] = episodic_summaries
                
                # Format episodic summaries
                episodic_lines = ["💬 Contesto recente conversazione:"]
                for episode in episodic_summaries[:episodic_top_k]:
                    text = episode.get("text", "")
                    if text:
                        # Truncate if too long
                        if len(text) > 200:
                            text = text[:200] + "..."
                        episodic_lines.append(f"  - {text}")
                
                episodic_section = "\n".join(episodic_lines)
                context_parts.append(episodic_section)
                
                log.debug(f"Episodic memory: {len(episodic_summaries)} episodes retrieved")
        
        except Exception as e:
            log.warning(f"Failed to retrieve episodic memory: {e}")
    
    # === ASSEMBLE AND TRIM ===
    if context_parts:
        context_text = "\n\n".join(context_parts)
        
        # Trim to token budget
        estimated_tokens = approx_tokens(context_text)
        if estimated_tokens > max_tokens:
            log.debug(f"Memory context trimmed: {estimated_tokens} → {max_tokens} tokens")
            context_text = trim_to_tokens(context_text, max_tokens)
            estimated_tokens = max_tokens
        
        result["context_text"] = context_text
        result["total_tokens"] = estimated_tokens
    
    return result


def save_to_memory(
    user_id: str,
    user_message: str,
    assistant_response: str,
    conversation_id: Optional[str] = None,
) -> Dict[str, any]:
    """
    Salva la nuova coppia domanda/risposta in memoria.
    
    - Aggiorna episodic memory (buffer conversazionale)
    - Rileva e salva nuovi user profile facts (se "ricorda che...")
    
    Args:
        user_id: ID utente
        user_message: Messaggio dell'utente
        assistant_response: Risposta dell'assistente
        conversation_id: ID conversazione
        
    Returns:
        Dict con status del salvataggio
    """
    result = {
        "episodic_saved": False,
        "profile_fact_saved": False,
        "needs_summarization": False,
    }
    
    # === EPISODIC MEMORY (buffer) ===
    if EPISODIC_ENABLED and EPISODIC_AVAILABLE and conversation_id:
        try:
            from core.episodic_memory import add_to_conversation_buffer
            
            buffer_result = add_to_conversation_buffer(
                conversation_id=conversation_id,
                user_message=user_message,
                assistant_message=assistant_response,
                user_id=user_id,
            )
            
            result["episodic_saved"] = buffer_result.get("added", False)
            result["needs_summarization"] = buffer_result.get("needs_summarization", False)
            
            log.debug(f"Episodic buffer: saved={result['episodic_saved']}, "
                     f"needs_sum={result['needs_summarization']}")
        
        except Exception as e:
            log.warning(f"Failed to save to episodic buffer: {e}")
    
    # === USER PROFILE (detect "remember" statements) ===
    if USER_PROFILE_ENABLED and PROFILE_AVAILABLE:
        try:
            from core.user_profile_memory import detect_remember_statement, save_user_profile_fact
            
            # Check if user said "remember that..."
            fact_text = detect_remember_statement(user_message)
            
            if fact_text:
                fact_id = save_user_profile_fact(
                    user_id=user_id,
                    fact_text=fact_text,
                )
                
                if fact_id:
                    result["profile_fact_saved"] = True
                    result["profile_fact_id"] = fact_id
                    log.info(f"Saved user profile fact: {fact_id}")
        
        except Exception as e:
            log.warning(f"Failed to save user profile fact: {e}")
    
    return result


async def maybe_summarize_buffer(
    conversation_id: str,
    user_id: Optional[str] = None,
    llm_func: Optional[any] = None,
) -> Optional[str]:
    """
    Controlla se il buffer episodico necessita summarization e la esegue.
    
    Args:
        conversation_id: ID conversazione
        user_id: ID utente
        llm_func: Funzione LLM async per generare summary
        
    Returns:
        Summary text se generato, None altrimenti
    """
    if not EPISODIC_ENABLED or not EPISODIC_AVAILABLE:
        return None
    
    try:
        from core.episodic_memory import get_current_buffer_status, summarize_and_save_buffer
        
        status = get_current_buffer_status(conversation_id)
        
        if status.get("needs_summarization", False):
            log.info(f"Buffer needs summarization: conv={conversation_id}")
            
            summary = await summarize_and_save_buffer(
                conversation_id=conversation_id,
                user_id=user_id,
                llm_func=llm_func,
            )
            
            return summary
    
    except Exception as e:
        log.warning(f"Failed to summarize buffer: {e}")
    
    return None
