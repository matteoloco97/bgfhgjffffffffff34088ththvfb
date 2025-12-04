#!/usr/bin/env python3
# core/chat_engine.py — LLM Chat Engine (robusto) con contesto temporale
# Patch 2025-11: endpoint robusto, hard-cap token budget, retry/backoff,
#                parsing OpenAI-compat, nessun errore testuale all’utente (raise)

from __future__ import annotations

import os, json, asyncio, time, math
from typing import Dict, Any, Optional
import requests
from dotenv import load_dotenv

# Import logging at module level
import logging

from core.datetime_helper import format_datetime_context

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

# === ENV config (coerente con quantum_api) ===
LLM_ENDPOINT_BASE = os.getenv("LLM_ENDPOINT", "http://127.0.0.1:9011/v1")
LLM_ENDPOINT = _build_chat_url(LLM_ENDPOINT_BASE)

LLM_MODEL = os.getenv("LLM_MODEL", "qwen2.5-32b-awq")
LLM_TEMPERATURE = _env_float("LLM_TEMPERATURE", 0.7)
LLM_MAX_TOKENS = _env_int("LLM_MAX_TOKENS", 512)

# Budget/contesto (hard cap)
LLM_MAX_CTX             = _env_int("LLM_MAX_CTX", 8192)
LLM_OUTPUT_BUDGET_TOK   = _env_int("LLM_OUTPUT_BUDGET_TOK", LLM_MAX_TOKENS)
LLM_SAFETY_MARGIN_TOK   = _env_int("LLM_SAFETY_MARGIN_TOK", 256)

# Timeout & retry
REQ_TIMEOUT_S = _env_float("LLM_HTTP_TIMEOUT_S", 60.0)
RETRY_ATTEMPTS = _env_int("LLM_RETRY_ATTEMPTS", 2)
RETRY_BACKOFF_S = _env_float("LLM_RETRY_BACKOFF_S", 0.6)

# === HTTP helper (async wrapper su requests) ===
async def _post(url: str, payload: dict, timeout: float) -> requests.Response:
    def _do():
        return requests.post(url, json=payload, timeout=timeout)
    return await asyncio.to_thread(_do)

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
    sys_trim = trim_to_tokens(sys_full, min(600, LLM_MAX_CTX // 8))  # persona non enorme
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
            r = await _post(LLM_ENDPOINT, payload, timeout=REQ_TIMEOUT_S)
            if r.status_code != 200:
                # prova a leggere un minimo di dettaglio per logging a monte
                try:
                    err_snip = (r.text or "")[:300]
                except Exception:
                    err_snip = f"HTTP {r.status_code}"
                raise RuntimeError(f"LLM HTTP {r.status_code}: {err_snip}")

            data = r.json()
            response_text = _extract_text(data)
            
            # Log timing
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            log.info(f"LLM response time: {elapsed_ms}ms")
            
            return response_text

        except (requests.exceptions.Timeout, asyncio.TimeoutError) as e:
            last_exc = e
        except requests.exceptions.ConnectionError as e:
            last_exc = e
        except Exception as e:
            last_exc = e

        # backoff tra i tentativi
        if attempt < (RETRY_ATTEMPTS + 1):
            await asyncio.sleep(RETRY_BACKOFF_S * attempt)

    # Se siamo qui, tutti i tentativi sono falliti → alza l’ultima eccezione
    raise RuntimeError(f"LLM failure after retries: {type(last_exc).__name__}: {last_exc}")

# === Synchronous fallback (stessa policy: raise su errori) ===
def reply_with_llm_sync(user_text: str, persona: str) -> str:
    payload = _build_payload(user_text, persona)

    attempts = RETRY_ATTEMPTS + 1
    last_exc: Optional[Exception] = None
    for attempt in range(1, attempts + 1):
        try:
            r = requests.post(LLM_ENDPOINT, json=payload, timeout=REQ_TIMEOUT_S)
            if r.status_code != 200:
                err_snip = (r.text or "")[:300]
                raise RuntimeError(f"LLM HTTP {r.status_code}: {err_snip}")
            data = r.json()
            response_text = _extract_text(data)
            
            # Log timing
            elapsed_ms = int((time.perf_counter() - t_start) * 1000)
            log.info(f"LLM response time: {elapsed_ms}ms")
            
            return response_text
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            last_exc = e
        except Exception as e:
            last_exc = e

        if attempt < attempts:
            time.sleep(RETRY_BACKOFF_S * attempt)

    raise RuntimeError(f"LLM failure after retries: {type(last_exc).__name__}: {last_exc}")

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
