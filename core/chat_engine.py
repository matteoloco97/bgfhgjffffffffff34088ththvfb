#!/usr/bin/env python3
# core/chat_engine.py — LLM Chat Engine (robusto) con contesto temporale
# Patch 2025-11: endpoint robusto, hard-cap token budget, retry/backoff,
#                parsing OpenAI-compat, nessun errore testuale all’utente (raise)

from __future__ import annotations

import os, json, asyncio, time, math
from typing import Dict, Any, Optional

# Import async HTTP client instead of requests
from core.async_http_client import get_http_client

from dotenv import load_dotenv

# Import logging at module level
import logging

from core.datetime_helper import format_datetime_context

# === Auto-Search Intelligence imports ===
# Imported at module level for better performance
from core.auto_search_detector import get_auto_search_detector
from core.query_classifier import get_query_classifier
from core.search_strategy_planner import get_search_strategy_planner

# === Token budget utils (fallback interni se modulo non presente) ===
try:
    from core.token_budget import approx_tokens, trim_to_tokens
except Exception:
    def approx_tokens(s: str) -> int:
        return math.ceil(len(s or "") / 4)
    def trim_to_tokens(s: str, max_tokens: int) -> str:
        if not s or max_tokens <= 0:
            return ""
        return s[: max_tokens * 4]

load_dotenv()

# Setup logging
log = logging.getLogger(__name__)

# === ENV helpers ===
def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        return int(__import__("re").search(r"-?\d+", raw).group(0))  # type: ignore
    except Exception:
        return int(default)

def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        return float(__import__("re").search(r"-?\d+(?:\.\d+)?", raw).group(0))  # type: ignore
    except Exception:
        return float(default)

def _build_chat_url(base_or_chat: str) -> str:
    """Normalizza endpoint in formato OpenAI /v1/chat/completions."""
    u = (base_or_chat or "").rstrip("/")
    if u.endswith("/chat/completions"):
        return u
    if u.endswith("/v1"):
        return f"{u}/chat/completions"
    # se arriva già con /v1/...
    if "/v1/" in u and not u.endswith("/chat/completions"):
        return f"{u.rstrip('/')}/chat/completions"
    return f"{u}/v1/chat/completions"

# === ENV config (OTTIMIZZATO per A6000 48GB) ===
# NOTA: Porta 5000 è il default per text-generation-webui API
# Per deployment esistenti su porta 9011, impostare LLM_ENDPOINT nel .env
LLM_ENDPOINT_BASE = os.getenv("LLM_ENDPOINT", "http://127.0.0.1:5000/v1")
LLM_ENDPOINT = _build_chat_url(LLM_ENDPOINT_BASE)

LLM_MODEL = os.getenv("LLM_MODEL", "DeepSeek-R1-Distill-Qwen-32B-abliterated-Q6_K")
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.7)  # Bilanciato: preciso ma creativo
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 4096)  # Risposte più lunghe (GPU 48GB)

# Budget/contesto (hard cap) - OTTIMIZZATO per A6000 48GB VRAM
LLM_MAX_CTX             = _env_int("LLM_MAX_CTX", 65536)  # 64K context (A6000 può gestirlo)
LLM_OUTPUT_BUDGET_TOK   = _env_int("LLM_OUTPUT_BUDGET_TOK", LLM_MAX_TOKENS)
LLM_SAFETY_MARGIN_TOK   = _env_int("LLM_SAFETY_MARGIN_TOK", 1024)  # Margine aumentato

# Timeout & retry - ottimizzati per modello 32B
REQ_TIMEOUT_S = _env_float("LLM_HTTP_TIMEOUT_S", 180.0)  # 3 minuti per risposte lunghe
RETRY_ATTEMPTS = _env_int("LLM_RETRY_ATTEMPTS", 3)
RETRY_BACKOFF_S = _env_float("LLM_RETRY_BACKOFF_S", 1.0)

# === HTTP helper (async using aiohttp) ===
async def _post(url: str, payload: dict, timeout: float) -> Dict[str, Any]:
    """
    Async HTTP POST using aiohttp.
    Returns the JSON response as a dict.
    """
    client = await get_http_client()
    if not client:
        raise RuntimeError("HTTP client not available")
    
    async with client.post(url, json=payload, timeout=timeout) as r:
        r.raise_for_status()
        return await r.json()

# === Payload builder + budget enforcement ===
def _build_payload(user_text: str, system_prompt: str) -> Dict[str, Any]:
    """Costruisce il payload OpenAI-compat rispettando l'hard-cap del contesto."""
    # Contesto temporale (sempre disponibile localmente)
    time_ctx = format_datetime_context()

    # Merge + trim del system prompt (persona + tempo)
    sys_full = (system_prompt or "").strip()
    sys_full = f"{sys_full}\n\n{time_ctx}".strip()

    # Hard cap input: (ctx - out_budget - safety)
    input_budget = max(512, LLM_MAX_CTX - LLM_OUTPUT_BUDGET_TOK - LLM_SAFETY_MARGIN_TOK)
    sys_trim = trim_to_tokens(sys_full, min(2000, LLM_MAX_CTX // 6))  # Persona più elaborata (da 600 a 2000 token max)
    user_trim = (user_text or "").strip()

    # Se sfora, taglia il messaggio utente dando priorità alla coda (informazione recente)
    tokens_now = approx_tokens(sys_trim) + approx_tokens(user_trim)
    if tokens_now > input_budget:
        keep_user = max(128, input_budget - approx_tokens(sys_trim))
        user_trim = trim_to_tokens(user_trim[-keep_user * 4 :], keep_user)

    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": sys_trim},
            {"role": "user", "content": user_trim},
        ],
        "temperature": float(LLM_TEMPERATURE),
        "max_tokens": int(LLM_OUTPUT_BUDGET_TOK),
        # opzionali, sicuri per la maggior parte dei back-end OpenAI-compat
        "top_p": 1.0,
        "n": 1,
    }
    return payload

# === Response parser robusto ===
def _extract_text(data: Dict[str, Any]) -> str:
    """
    Estrae il testo dalla risposta OpenAI-compat.
    Supporta varianti minimali.
    Alza ValueError se mancante.
    """
    try:
        choices = data.get("choices") or []
        if not choices:
            raise ValueError("choices vuoto")
        msg = choices[0].get("message") or {}
        content = (msg.get("content") or "").strip()
        if content:
            return content
        # Alcuni provider usano 'text' direttamente
        txt = (choices[0].get("text") or "").strip()
        if txt:
            return txt
        raise ValueError("contenuto mancante")
    except Exception as e:
        raise ValueError(f"Formato risposta inatteso: {e}")

# === Main async API ===
async def reply_with_llm(
    user_text: str, 
    persona: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    stop_sequences: Optional[list] = None,
    repetition_penalty: Optional[float] = None,
) -> str:
    """
    Chiama il modello e RITORNA solo testo.
    Non restituisce stringhe di errore visibili all'utente:
    in caso di problemi alza eccezioni (gestite dal chiamante).
    
    Parameters
    ----------
    user_text : str
        Testo del messaggio utente.
    persona : str
        System prompt/persona per il contesto.
    temperature : float, optional
        Override della temperatura (default da env LLM_TEMPERATURE).
    max_tokens : int, optional
        Override del max tokens (default da env LLM_MAX_TOKENS).
    stop_sequences : list, optional
        Sequenze di stop opzionali.
    repetition_penalty : float, optional
        Penalità per ripetizioni (supporto dipende dal backend).
    
    Returns
    -------
    str
        Risposta del modello LLM.
    
    Raises
    ------
    RuntimeError
        Se tutti i tentativi falliscono.
    """
    t_start = time.perf_counter()
    
    payload = _build_payload(user_text, persona)

    # Apply optional overrides
    if temperature is not None:
        payload["temperature"] = float(temperature)
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    if stop_sequences is not None and stop_sequences:
        payload["stop"] = stop_sequences
    if repetition_penalty is not None:
        # Some backends support this, others ignore it
        payload["repetition_penalty"] = float(repetition_penalty)

    last_exc: Optional[Exception] = None
    for attempt in range(1, RETRY_ATTEMPTS + 2):  # es. 1 tentativo + 2 retry = 3 tot
        try:
            data = await _post(LLM_ENDPOINT, payload, timeout=REQ_TIMEOUT_S)
            response_text = _extract_text(data)
            
            # Log timing
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            log.info(f"LLM response time: {elapsed_ms}ms")
            
            return response_text

        except asyncio.TimeoutError as e:
            last_exc = e
        except Exception as e:
            last_exc = e

        # backoff tra i tentativi
        if attempt < (RETRY_ATTEMPTS + 1):
            await asyncio.sleep(RETRY_BACKOFF_S * attempt)

    # Se siamo qui, tutti i tentativi sono falliti → alza l’ultima eccezione
    raise RuntimeError(f"LLM failure after retries: {type(last_exc).__name__}: {last_exc}")

# === Synchronous fallback (DEPRECATED - use async version) ===
# NOTE: This function is deprecated and should not be used in new code.
# Use reply_with_llm() instead which is fully async.
def reply_with_llm_sync(user_text: str, persona: str) -> str:
    """
    DEPRECATED: Synchronous version of reply_with_llm.
    Use reply_with_llm() instead for better performance with async HTTP.
    
    This function wraps the async version in asyncio.run() for backward compatibility.
    """
    import warnings
    warnings.warn(
        "reply_with_llm_sync is deprecated, use async reply_with_llm instead",
        DeprecationWarning,
        stacklevel=2
    )
    return asyncio.run(reply_with_llm(user_text, persona))


# === Streaming API ===
async def reply_with_llm_streaming(
    user_text: str,
    persona: str,
    temperature: Optional[float] = None,
    max_tokens: Optional[int] = None,
    stop_sequences: Optional[list] = None,
    repetition_penalty: Optional[float] = None,
):
    """
    Stream LLM response token-by-token using OpenAI-compatible streaming API.
    
    This function yields individual tokens as they are generated by the LLM,
    allowing for progressive response delivery to the client.
    
    Parameters
    ----------
    user_text : str
        User message text.
    persona : str
        System prompt/persona for context.
    temperature : float, optional
        Override temperature (default from env LLM_TEMPERATURE).
    max_tokens : int, optional
        Override max tokens (default from env LLM_MAX_TOKENS).
    stop_sequences : list, optional
        Optional stop sequences.
    repetition_penalty : float, optional
        Repetition penalty (support depends on backend).
    
    Yields
    ------
    dict
        Dictionary with 'type' field indicating message type:
        - {'type': 'token', 'text': str} for each token
        - {'type': 'done', 'total_tokens': int} when complete
        - {'type': 'error', 'message': str} on error
    
    Raises
    ------
    RuntimeError
        If all retry attempts fail (after yielding already sent tokens).
    """
    import aiohttp
    
    t_start = time.perf_counter()
    
    payload = _build_payload(user_text, persona)
    
    # Enable streaming in the payload
    payload["stream"] = True

    # Apply optional overrides
    if temperature is not None:
        payload["temperature"] = float(temperature)
    if max_tokens is not None:
        payload["max_tokens"] = int(max_tokens)
    if stop_sequences is not None and stop_sequences:
        payload["stop"] = stop_sequences
    if repetition_penalty is not None:
        payload["repetition_penalty"] = float(repetition_penalty)

    total_tokens = 0
    accumulated_text = ""
    
    # Retry logic for streaming (initial attempt + retries)
    max_attempts = RETRY_ATTEMPTS + 1
    for attempt in range(1, max_attempts + 1):
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    LLM_ENDPOINT,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=REQ_TIMEOUT_S)
                ) as response:
                    
                    if response.status != 200:
                        error_text = await response.text()
                        error_msg = f"LLM HTTP {response.status}: {error_text[:300]}"
                        log.error(error_msg)
                        
                        # If this is not the last attempt, retry
                        if attempt < max_attempts:
                            await asyncio.sleep(RETRY_BACKOFF_S * attempt)
                            continue
                        
                        # Last attempt failed, yield error
                        yield {
                            "type": "error",
                            "message": error_msg,
                            "code": f"http_{response.status}"
                        }
                        return
                    
                    # Stream response chunks
                    async for line in response.content:
                        line_str = line.decode('utf-8').strip()
                        
                        # Skip empty lines
                        if not line_str:
                            continue
                        
                        # SSE format: lines start with "data: "
                        if line_str.startswith("data: "):
                            data_str = line_str[6:]  # Remove "data: " prefix
                            
                            # Check for stream end marker
                            if data_str == "[DONE]":
                                break
                            
                            try:
                                chunk_data = json.loads(data_str)
                                
                                # Extract token from OpenAI-compatible format
                                choices = chunk_data.get("choices", [])
                                if choices:
                                    delta = choices[0].get("delta", {})
                                    content = delta.get("content", "")
                                    
                                    if content:
                                        accumulated_text += content
                                        # Note: This is a chunk count, not actual token count
                                        # Actual token count is reported by the LLM in done message
                                        total_tokens += 1
                                        
                                        yield {
                                            "type": "token",
                                            "text": content,
                                            "index": total_tokens - 1
                                        }
                                    
                                    # Check for finish reason
                                    finish_reason = choices[0].get("finish_reason")
                                    if finish_reason:
                                        break
                                        
                            except json.JSONDecodeError:
                                log.warning(f"Failed to parse streaming chunk: {data_str[:100]}")
                                continue
                    
                    # Successful stream completion
                    elapsed_ms = int((time.perf_counter() - t_start) * 1000)
                    log.info(f"LLM streaming response: {total_tokens} tokens in {elapsed_ms}ms")
                    
                    yield {
                        "type": "done",
                        "total_tokens": total_tokens,
                        "text": accumulated_text,
                        "elapsed_ms": elapsed_ms
                    }
                    return
                    
        except asyncio.TimeoutError as e:
            log.warning(f"Streaming timeout on attempt {attempt}")
            if attempt < max_attempts:
                await asyncio.sleep(RETRY_BACKOFF_S * attempt)
                continue
            
            # Timeout on last attempt
            yield {
                "type": "error",
                "message": "Stream timeout",
                "code": "timeout"
            }
            return
            
        except Exception as e:
            log.error(f"Streaming error on attempt {attempt}: {e}")
            if attempt < max_attempts:
                await asyncio.sleep(RETRY_BACKOFF_S * attempt)
                continue
            
            # Error on last attempt
            yield {
                "type": "error",
                "message": str(e),
                "code": "stream_error"
            }
            return


# === Test rapido ===
if __name__ == "__main__":
    print("🧪 CHAT ENGINE - TEST\n" + "=" * 60)
    test_persona = (
        "Sei un assistente AI conciso e utile. "
        "Rispondi sempre in modo diretto e professionale."
    )
    tests = ["Ciao!", "Che giorno è oggi?", "Spiegami la differenza tra RAM e ROM in 3 frasi."]

    async def _run():
        for q in tests:
            print(f"User: {q}")
            try:
                ans = await reply_with_llm(q, test_persona)
                print("Bot :", ans[:200], "\n")
            except Exception as e:
                print("ERR :", e, "\n")

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("Interrotto.")


# ==================== Auto Web Search Intelligence Integration ====================

async def process_with_auto_search(
    user_message: str,
    user_id: str,
    context: Optional[Dict[str, Any]] = None,
    persona: str = ""
) -> Dict[str, Any]:
    """
    New intelligent flow with auto-search detection.
    
    Flow:
    1. Classify intent (conversational/factual/live_data/research)
    2. If conversational → direct response
    3. If factual → check memory, then search if gap
    4. If live_data → ALWAYS search with optimized strategy
    5. If research → deep search multi-source
    
    Parameters
    ----------
    user_message : str
        The user's message/query.
    user_id : str
        User identifier for memory context.
    context : Dict, optional
        Additional context information.
    persona : str
        System prompt/persona for the response.
    
    Returns
    -------
    Dict[str, Any]
        {
            'response': str,
            'sources': List[Dict],
            'search_triggered': bool,
            'search_reason': str,
            'confidence': float
        }
    """
    context = context or {}
    
    # Get detector and classifier instances
    detector = get_auto_search_detector()
    classifier = get_query_classifier()
    planner = get_search_strategy_planner()
    
    # Step 1: Classify intent
    intent_result = await classifier.classify_intent(user_message, context)
    intent = intent_result.get('intent', 'factual')
    
    log.info(f"Auto-search: intent={intent}, confidence={intent_result.get('confidence', 0):.2f}")
    
    # Step 2: Check if search should be triggered
    user_memory = context.get('user_memory', {})
    search_decision = await detector.should_trigger_search(user_message, context, user_memory)
    
    should_search = search_decision.get('should_search', False)
    search_reason = search_decision.get('search_reason', 'none')
    search_type = search_decision.get('search_type', 'none')
    
    # Step 3: Handle based on intent
    if intent == 'conversational' and not should_search:
        # Direct LLM response for conversational
        try:
            response = await reply_with_llm(user_message, persona)
            return {
                'response': response,
                'sources': [],
                'search_triggered': False,
                'search_reason': 'conversational',
                'confidence': intent_result.get('confidence', 0.9)
            }
        except Exception as e:
            log.error(f"LLM error in conversational: {e}")
            return {
                'response': "Mi dispiace, c'è stato un problema nel generare la risposta.",
                'sources': [],
                'search_triggered': False,
                'search_reason': 'error',
                'confidence': 0.0
            }
    
    if intent == 'calculation':
        # Handle calculation directly
        try:
            response = await reply_with_llm(user_message, persona)
            return {
                'response': response,
                'sources': [],
                'search_triggered': False,
                'search_reason': 'calculation',
                'confidence': intent_result.get('confidence', 0.95)
            }
        except Exception as e:
            log.error(f"LLM error in calculation: {e}")
            return {
                'response': "Errore nel calcolo. Riprova.",
                'sources': [],
                'search_triggered': False,
                'search_reason': 'error',
                'confidence': 0.0
            }
    
    # Step 4: Handle live_data or search-required queries
    if should_search or intent in ['live_data', 'research', 'factual']:
        data_type = search_decision.get('data_type', intent_result.get('sub_intent', 'general'))
        
        # Get search strategy
        strategy = await planner.plan_search_strategy(user_message, intent_result)
        
        # Handle live data query
        if intent == 'live_data' or data_type in ['price', 'weather', 'news', 'sports']:
            return await _handle_live_data_query(user_message, data_type, context, persona, strategy)
        
        # Handle research query
        if intent == 'research':
            return await _handle_research_query(user_message, context, persona, strategy)
        
        # Handle factual query with potential search
        return await _handle_factual_query(user_message, context, persona, strategy, intent_result)
    
    # Default: Direct LLM response
    try:
        response = await reply_with_llm(user_message, persona)
        return {
            'response': response,
            'sources': [],
            'search_triggered': False,
            'search_reason': 'default_llm',
            'confidence': 0.6
        }
    except Exception as e:
        log.error(f"LLM error: {e}")
        return {
            'response': "Mi dispiace, si è verificato un errore.",
            'sources': [],
            'search_triggered': False,
            'search_reason': 'error',
            'confidence': 0.0
        }


async def _handle_live_data_query(
    query: str,
    data_type: str,
    context: Dict[str, Any],
    persona: str,
    strategy: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle specialized live data query.
    
    Routes to specific tool (price_tool, weather_tool).
    Bypasses cache if expired.
    Uses concise synthesis.
    """
    from core.web_search import smart_search, adaptive_synthesis
    
    log.info(f"Handling live data query: type={data_type}")
    
    try:
        # Perform smart search
        search_result = await smart_search(
            query,
            strategy,
            {'intent': 'live_data', 'sub_intent': data_type}
        )
        
        results = search_result.get('results', [])
        
        if not results:
            # Fallback to LLM with context about no results
            response = await reply_with_llm(
                f"Non ho trovato informazioni aggiornate su: {query}. "
                "Basandomi sulla mia conoscenza, rispondo: " + query,
                persona
            )
            return {
                'response': response,
                'sources': [],
                'search_triggered': True,
                'search_reason': f'live_data:{data_type}',
                'confidence': 0.5
            }
        
        # Synthesize results
        synthesis_mode = strategy.get('synthesis_mode', 'concise')
        synthesized = adaptive_synthesis(results, synthesis_mode)
        
        # Build response with LLM
        synthesis_prompt = (
            f"Basandoti su queste informazioni recenti:\n\n{synthesized}\n\n"
            f"Rispondi alla domanda: {query}"
        )
        
        response = await reply_with_llm(synthesis_prompt, persona)
        
        sources = [{'url': r.get('url', ''), 'title': r.get('title', '')} 
                   for r in results[:3]]
        
        return {
            'response': response,
            'sources': sources,
            'search_triggered': True,
            'search_reason': f'live_data:{data_type}',
            'confidence': 0.85
        }
        
    except Exception as e:
        log.error(f"Live data query error: {e}")
        return {
            'response': f"Errore nel recupero dati live: {str(e)}",
            'sources': [],
            'search_triggered': True,
            'search_reason': 'error',
            'confidence': 0.0
        }


async def _handle_research_query(
    query: str,
    context: Dict[str, Any],
    persona: str,
    strategy: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle deep research query.
    
    Multi-source search, deep synthesis, source citation.
    """
    from core.web_search import smart_search, adaptive_synthesis
    
    log.info(f"Handling research query")
    
    try:
        # Perform comprehensive search
        search_result = await smart_search(
            query,
            strategy,
            {'intent': 'research', 'sub_intent': 'deep_research'}
        )
        
        results = search_result.get('results', [])
        
        if not results:
            response = await reply_with_llm(query, persona)
            return {
                'response': response,
                'sources': [],
                'search_triggered': True,
                'search_reason': 'research',
                'confidence': 0.6
            }
        
        # Comprehensive synthesis
        synthesized = adaptive_synthesis(results, 'comprehensive')
        
        synthesis_prompt = (
            f"Fornisci una risposta dettagliata e approfondita basandoti su queste fonti:\n\n"
            f"{synthesized}\n\n"
            f"Domanda originale: {query}\n\n"
            "Includi informazioni chiave e cita le fonti quando appropriato."
        )
        
        response = await reply_with_llm(synthesis_prompt, persona)
        
        sources = [{'url': r.get('url', ''), 'title': r.get('title', '')} 
                   for r in results[:5]]
        
        return {
            'response': response,
            'sources': sources,
            'search_triggered': True,
            'search_reason': 'research',
            'confidence': 0.88
        }
        
    except Exception as e:
        log.error(f"Research query error: {e}")
        return {
            'response': f"Errore nella ricerca approfondita: {str(e)}",
            'sources': [],
            'search_triggered': True,
            'search_reason': 'error',
            'confidence': 0.0
        }


async def _handle_factual_query(
    query: str,
    context: Dict[str, Any],
    persona: str,
    strategy: Dict[str, Any],
    intent_result: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Handle factual query with optional search.
    
    Checks memory first, then searches if knowledge gap detected.
    """
    from core.web_search import smart_search, adaptive_synthesis
    
    log.info(f"Handling factual query")
    
    try:
        # Check if search is really needed based on urgency
        urgency = intent_result.get('search_urgency', 'low')
        
        if urgency == 'none':
            # No search needed, use LLM directly
            response = await reply_with_llm(query, persona)
            return {
                'response': response,
                'sources': [],
                'search_triggered': False,
                'search_reason': 'factual_no_search',
                'confidence': intent_result.get('confidence', 0.7)
            }
        
        # Perform search
        search_result = await smart_search(
            query,
            strategy,
            intent_result
        )
        
        results = search_result.get('results', [])
        
        if not results:
            response = await reply_with_llm(query, persona)
            return {
                'response': response,
                'sources': [],
                'search_triggered': True,
                'search_reason': 'factual_no_results',
                'confidence': 0.6
            }
        
        # Synthesize
        synthesized = adaptive_synthesis(results, 'detailed')
        
        synthesis_prompt = (
            f"Rispondi alla domanda basandoti su queste informazioni:\n\n"
            f"{synthesized}\n\n"
            f"Domanda: {query}"
        )
        
        response = await reply_with_llm(synthesis_prompt, persona)
        
        sources = [{'url': r.get('url', ''), 'title': r.get('title', '')} 
                   for r in results[:3]]
        
        return {
            'response': response,
            'sources': sources,
            'search_triggered': True,
            'search_reason': 'factual',
            'confidence': 0.80
        }
        
    except Exception as e:
        log.error(f"Factual query error: {e}")
        return {
            'response': f"Errore nel processare la domanda: {str(e)}",
            'sources': [],
            'search_triggered': True,
            'search_reason': 'error',
            'confidence': 0.0
        }
