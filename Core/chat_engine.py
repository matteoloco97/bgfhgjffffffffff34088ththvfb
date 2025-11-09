#!/usr/bin/env python3
# core/chat_engine.py - LLM Chat Engine with Temporal Context

import json
import asyncio
import os
import requests
from dotenv import load_dotenv
from core.datetime_helper import format_datetime_context

load_dotenv()

# === ENV Configuration ===
LLM_ENDPOINT_BASE = os.getenv("LLM_ENDPOINT", "http://127.0.0.1:9001/v1")
LLM_MODEL = os.getenv("LLM_MODEL", "llama-3.1-70b")
LLM_TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", 0.7))
LLM_MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", 512))

# Costruisci URL completo per chat/completions
if LLM_ENDPOINT_BASE.endswith("/chat/completions"):
    LLM_ENDPOINT = LLM_ENDPOINT_BASE
elif LLM_ENDPOINT_BASE.endswith("/v1"):
    LLM_ENDPOINT = f"{LLM_ENDPOINT_BASE}/chat/completions"
else:
    LLM_ENDPOINT = f"{LLM_ENDPOINT_BASE}/v1/chat/completions"

# === Helper Functions ===

async def _post(url: str, payload: dict, timeout: int = 60):
    """Wrapper async per requests.post"""
    return await asyncio.to_thread(
        lambda: requests.post(url, json=payload, timeout=timeout)
    )

# === Main Chat Function ===

async def reply_with_llm(user_text: str, persona: str) -> str:
    """
    Chiama LLM con formato OpenAI-compatible + temporal context.
    
    Args:
        user_text: Testo dell'utente
        persona: System prompt (personalità del bot)
    
    Returns:
        Risposta del LLM come stringa
    """
    
    # ✅ TEMPORAL CONTEXT
    time_context = format_datetime_context()
    
    # ✅ SYSTEM PROMPT COMPLETO
    # Persona base + contesto temporale
    system_prompt = persona
    system_prompt += f"\n\n{time_context}"
    
    # ✅ PAYLOAD OpenAI-COMPATIBLE
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS
    }
    
    try:
        # Chiamata al LLM
        r = await _post(LLM_ENDPOINT, payload, timeout=60)
        
        # Check status
        if r.status_code != 200:
            error_text = r.text[:300] if r.text else "Unknown error"
            return f"❌ LLM error {r.status_code}: {error_text}"
        
        # Parse response
        data = r.json()
        
        try:
            # Estrai contenuto dalla risposta OpenAI-format
            response_text = data["choices"][0]["message"]["content"].strip()
            return response_text
        
        except (KeyError, IndexError) as e:
            # Formato risposta inatteso
            return (
                f"❌ Formato risposta inatteso: {e}\n"
                f"Response preview: {json.dumps(data, ensure_ascii=False)[:500]}"
            )
    
    except asyncio.TimeoutError:
        return "❌ Timeout: il LLM sta impiegando troppo tempo. Riprova."
    
    except requests.exceptions.ConnectionError:
        return "❌ Impossibile connettersi al LLM. Verifica che sia attivo."
    
    except Exception as e:
        return f"❌ Errore LLM: {type(e).__name__}: {str(e)}"


# === Alternative: Simple Sync Version (Backup) ===

def reply_with_llm_sync(user_text: str, persona: str) -> str:
    """
    Versione sincrona di reply_with_llm (fallback).
    
    Usa solo se hai problemi con async.
    """
    
    time_context = format_datetime_context()
    system_prompt = persona + f"\n\n{time_context}"
    
    payload = {
        "model": LLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text}
        ],
        "temperature": LLM_TEMPERATURE,
        "max_tokens": LLM_MAX_TOKENS
    }
    
    try:
        r = requests.post(LLM_ENDPOINT, json=payload, timeout=60)
        
        if r.status_code != 200:
            return f"❌ LLM error {r.status_code}: {r.text[:300]}"
        
        data = r.json()
        return data["choices"][0]["message"]["content"].strip()
    
    except Exception as e:
        return f"❌ Errore LLM: {e}"


# === TESTING ===

if __name__ == "__main__":
    import asyncio
    
    print("🧪 CHAT ENGINE - TEST\n")
    print("=" * 60)
    
    # Test persona
    test_persona = (
        "Sei un assistente AI conciso e utile. "
        "Rispondi sempre in modo diretto e professionale."
    )
    
    # Test queries
    test_queries = [
        "Ciao, come stai?",
        "Che giorno è oggi?",
        "Quanto fa 2+2?",
    ]
    
    async def run_tests():
        print("📝 Test Queries:\n")
        
        for query in test_queries:
            print(f"User: {query}")
            
            try:
                response = await reply_with_llm(query, test_persona)
                print(f"Bot:  {response[:200]}")
                print()
            except Exception as e:
                print(f"❌ Error: {e}\n")
        
        print("=" * 60)
        print("✅ CHAT ENGINE - TEST COMPLETE\n")
    
    # Run
    try:
        asyncio.run(run_tests())
    except KeyboardInterrupt:
        print("\n⚠️  Test interrotto")
    except Exception as e:
        print(f"\n❌ Test fallito: {e}")
