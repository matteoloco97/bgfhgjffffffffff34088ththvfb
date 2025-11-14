# agents/web_research_agent.py — WebResearchAgent (versione semplificata ma aggressiva)
# Obiettivo: dare SEMPRE una risposta utile, anche se i dati non sono perfetti.
#
# - Usa core.web_search.search per trovare le fonti
# - Legge 2–3 pagine con fetch_and_extract
# - Chiede al modello una risposta diretta + fonti
# - Vietato rispondere solo "le fonti non contengono..." se esistono info utili

from __future__ import annotations
import os
import asyncio
import time
from typing import Any, Dict, List, Optional

from core.web_tools import fetch_and_extract
from core.chat_engine import reply_with_llm

# web_search è sincrona, ma la usiamo direttamente (come in _web_search_pipeline)
try:
    from core.web_search import search as web_search_simple
except Exception:
    web_search_simple = None  # type: ignore

# Per limitare il contesto
try:
    from core.token_budget import trim_to_tokens
except Exception:
    # fallback banale
    def trim_to_tokens(s: str, max_tokens: int) -> str:
        if not s or max_tokens <= 0:
            return ""
        max_chars = max_tokens * 4
        return s[:max_chars]

WEB_RESEARCH_BUDGET_TOK = int(os.getenv("WEB_RESEARCH_BUDGET_TOK", "1500"))
WEB_RESEARCH_FETCH_TIMEOUT_S = float(os.getenv("WEB_RESEARCH_FETCH_TIMEOUT_S", "6.0"))
WEB_RESEARCH_MAX_DOCS = int(os.getenv("WEB_RESEARCH_MAX_DOCS", "3"))

class WebResearchAgent:
    """
    Orchestratore di ricerca web multi-step (semplificato).

    API:
        result = await WebResearchAgent().research(query="...", persona="...")
        ritorna:
        {
          "answer": str,
          "sources": [{"url":..., "title":...}, ...],
          "steps": [{"step": 1, "query": "...", "results_count": int,
                     "docs_read": int, "novelty": float}],
          "total_steps": int,
          "note": str opzionale
        }
    """

    def __init__(self) -> None:
        self.max_docs = max(1, WEB_RESEARCH_MAX_DOCS)

    async def _fetch_docs(self, results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Scarica e pulisce il testo da un piccolo numero di URL."""
        extracts: List[Dict[str, Any]] = []

        async def _one(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            url = item.get("url") or ""
            if not url:
                return None
            try:
                text, _ = await asyncio.wait_for(
                    fetch_and_extract(url),
                    timeout=WEB_RESEARCH_FETCH_TIMEOUT_S
                )
            except asyncio.TimeoutError:
                return None
            except Exception:
                return None
            if not text:
                return None
            trimmed = trim_to_tokens(text, WEB_RESEARCH_BUDGET_TOK // self.max_docs)
            return {
                "url": url,
                "title": item.get("title") or url,
                "text": trimmed,
            }

        tasks = [asyncio.create_task(_one(r)) for r in results[: self.max_docs]]
        done = await asyncio.gather(*tasks, return_exceptions=True)
        for d in done:
            if isinstance(d, dict) and d.get("text"):
                extracts.append(d)
        return extracts

    async def research(self, query: str, persona: str) -> Dict[str, Any]:
        t0 = time.perf_counter()
        steps: List[Dict[str, Any]] = []

        # STEP 1: ricerca SERP
        if not web_search_simple:
            return {
                "answer": "Il motore di ricerca interno non è configurato.",
                "sources": [],
                "steps": [],
                "total_steps": 0,
                "note": "web_search_unavailable",
            }

        results: List[Dict[str, Any]] = []
        try:
            results = web_search_simple(query, num=8) or []
        except Exception:
            results = []

        steps.append(
            {
                "step": 1,
                "query": query,
                "results_count": len(results),
                "docs_read": 0,
                "novelty": 1.0,
            }
        )

        if not results:
            return {
                "answer": "Non ho trovato risultati affidabili per quella ricerca. "
                          "Prova a riformulare la domanda o ad aggiungere dettagli (data, luogo, sito, ecc.).",
                "sources": [],
                "steps": steps,
                "total_steps": 1,
                "note": "empty_serp",
            }

        # STEP 2: lettura pagine
        extracts = await self._fetch_docs(results)
        steps[-1]["docs_read"] = len(extracts)

        # Se proprio non riusciamo a leggere testo, almeno restituiamo le fonti
        if not extracts:
            srcs = [{"url": r.get("url"), "title": r.get("title") or r.get("url")} for r in results[:3]]
            return {
                "answer": (
                    "Ho trovato alcune fonti pertinenti ma non sono riuscito a leggerne il contenuto in modo affidabile. "
                    "Apri uno di questi link per vedere i dettagli aggiornati."
                ),
                "sources": srcs,
                "steps": steps,
                "total_steps": 2,
                "note": "no_extracts",
            }

        # Costruisci contesto
        ctx_parts = []
        sources: List[Dict[str, str]] = []
        for e in extracts:
            ctx_parts.append(
                f"### {e['title']}\nURL: {e['url']}\n\n{e['text']}"
            )
            sources.append({"url": e["url"], "title": e["title"]})
        ctx = "\n\n".join(ctx_parts)
        ctx = trim_to_tokens(ctx, WEB_RESEARCH_BUDGET_TOK)

        # Prompt finale: OBBLIGATO a rispondere
        user_prompt = (
            "Stai facendo ricerca su internet per rispondere alla DOMANDA seguente.\n"
            "Hai a disposizione estratti da più pagine web.\n\n"
            "REGOLE IMPORTANTI:\n"
            "1) Dai SEMPRE una risposta chiara e utile in ITALIANO, in 3–6 frasi.\n"
            "2) Usa i numeri e i dettagli che trovi negli estratti. Se il dato è live "
            "(prezzi, meteo, risultati, orari) o potrebbe cambiare, scrivi chiaramente "
            "che si tratta del valore attuale/approssimativo e che può variare.\n"
            "3) Se le fonti non contengono il numero preciso o il dettaglio esatto, NON dire solo "
            "\"le fonti non contengono\". Invece:\n"
            "   - spiega cosa dicono le fonti,\n"
            "   - riassumi le informazioni disponibili,\n"
            "   - indica cosa manca e cosa l'utente dovrebbe controllare aprendo i link.\n"
            "4) Evita formulazioni vaghe; sii concreto e pratico.\n"
            "5) Concludi SEMPRE con una riga finale del tipo: "
            "\"Fonti: URL1[, URL2, URL3]\" usando le URL più rilevanti.\n\n"
            f"DOMANDA: {query}\n\n"
            "=== ESTRATTI WEB ===\n"
            f"{ctx}\n"
        )

        try:
            answer_text = await reply_with_llm(user_prompt, persona or "Sei una GPT neutra e modulare.")
        except Exception:
            # fallback minimalista ma comunque utile
            answer_text = (
                "Ho avuto un problema nel generare una sintesi automatica, ma ho trovato alcune fonti "
                "pertinenti che puoi consultare direttamente.\n"
            )

        answer_text = (answer_text or "").strip()
        if not answer_text:
            answer_text = (
                "Non sono riuscito a generare una risposta strutturata, ma le fonti qui sotto "
                "contengono comunque informazioni utili sull'argomento. Aprile per i dettagli."
            )

        total_steps = len(steps)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        steps.append(
            {
                "step": total_steps + 1,
                "query": query,
                "results_count": len(results),
                "docs_read": len(extracts),
                "novelty": 0.0,
                "elapsed_ms": elapsed_ms,
            }
        )

        return {
            "answer": answer_text,
            "sources": sources,
            "steps": steps,
            "total_steps": len(steps),
            "note": "ok",
        }
