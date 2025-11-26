# agents/web_research_agent.py — WebResearchAgent (versione semplificata ma AGGRESSIVA)
# Obiettivo: dare SEMPRE una risposta utile e concreta, usando SOLO ciò che è negli estratti.
#
# - Usa core.web_search.search per trovare le fonti
# - Legge 2–3 pagine con fetch_and_extract
# - Chiede al modello una risposta diretta + fonti
# - Vietato limitarsi a dire "le fonti non contengono..." se esistono info utili
# - Niente "apri la fonte" come unica soluzione: la risposta deve essere autosufficiente

from __future__ import annotations

import os
import time
import asyncio
import logging
from typing import Any, Dict, List, Optional

from core.web_tools import fetch_and_extract
from core.chat_engine import reply_with_llm

log = logging.getLogger(__name__)

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
    Orchestratore di ricerca web multi-step (semplificato ma aggressivo).

    API:
        result = await WebResearchAgent().research(query="...", persona="...")
        ritorna:
        {
          "answer": str,
          "sources": [{"url":..., "title":...}, ...],
          "steps": [{"step": 1, "query": "...", "results_count": int,
                     "docs_read": int, "novelty": float, ...}],
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
                    timeout=WEB_RESEARCH_FETCH_TIMEOUT_S,
                )
            except asyncio.TimeoutError:
                return None
            except Exception:
                return None

            if not text:
                return None

            trimmed = trim_to_tokens(
                text, WEB_RESEARCH_BUDGET_TOK // self.max_docs
            )
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
        note: str = "ok"

        # STEP 1: ricerca SERP
        if not web_search_simple:
            return {
                "answer": (
                    "Il motore di ricerca interno non è configurato, quindi non posso "
                    "eseguire la ricerca sul web."
                ),
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
            # SERP completamente vuota: niente fluenza inutile, risposta diretta
            return {
                "answer": (
                    "Non ho trovato risultati affidabili collegati alla tua richiesta nei motori "
                    "di ricerca utilizzati. Se puoi, prova a riformulare indicando più dettagli "
                    "(ad esempio data, luogo, competizione, sito di riferimento o il contesto "
                    "specifico) così la ricerca può essere più mirata."
                ),
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
            srcs = [
                {"url": r.get("url"), "title": r.get("title") or r.get("url")}
                for r in results[:3]
                if r.get("url")
            ]
            return {
                "answer": (
                    "Ho individuato alcune pagine potenzialmente rilevanti, ma non sono riuscito "
                    "a estrarne il contenuto in modo affidabile (timeout o errore di lettura). "
                    "Le URL che ho trovato possono comunque contenere informazioni utili "
                    "sull'argomento."
                ),
                "sources": srcs,
                "steps": steps,
                "total_steps": 2,
                "note": "no_extracts",
            }

        # Costruisci contesto
        ctx_parts: List[str] = []
        sources: List[Dict[str, str]] = []

        for e in extracts:
            ctx_parts.append(
                f"### {e['title']}\nURL: {e['url']}\n\n{e['text']}"
            )
            sources.append({"url": e["url"], "title": e["title"]})

        ctx = "\n\n".join(ctx_parts)
        ctx = trim_to_tokens(ctx, WEB_RESEARCH_BUDGET_TOK)

        # === Prompt finale ULTRA-AGGRESSIVO V2 (con regole anti-evasive) ===
        user_prompt = (
            "CONTESTO: Sei un ricercatore esperto che DEVE SEMPRE fornire valore massimo, "
            "anche con informazioni parziali o incomplete.\n"
            "\n"
            "HAI A DISPOSIZIONE questi estratti da pagine web:\n"
            f"{ctx}\n"
            "\n"
            "DOMANDA UTENTE:\n"
            f"{query}\n"
            "\n"
            "=== REGOLE CRITICHE (VIOLAZIONE = FALLIMENTO) ===\n"
            "\n"
            "1. **VIETATO ASSOLUTAMENTE**:\n"
            "   - Dire 'non ho abbastanza informazioni'\n"
            "   - Dire 'le fonti non contengono'\n"
            "   - Dire 'consulta/apri/visita le fonti'\n"
            "   - Dire 'per maggiori dettagli vai a...'\n"
            "   - Qualsiasi frase che rimanda l'utente altrove\n"
            "\n"
            "2. **OBBLIGATORIO**:\n"
            "   - Sintetizza TUTTO ciò che è presente negli estratti\n"
            "   - Se mancano dati specifici, usa: 'Gli estratti coprono [A, B, C] ma non "
            "menzionano [X]'\n"
            "   - SEMPRE fornire almeno 3-4 facts concreti trovati\n"
            "   - Se informazioni parziali, dillo ma poi fornisci quello che c'è\n"
            "\n"
            "3. **NUMERI E DATI**:\n"
            "   - Se trovi numeri (prezzi, date, %, quantità), riportali CON UNITÀ\n"
            "   - Esempio CORRETTO: 'Il prezzo attuale è €45.50'\n"
            "   - Esempio SBAGLIATO: 'Il prezzo è indicato nelle fonti'\n"
            "\n"
            "4. **FORMATO RISPOSTA**:\n"
            "   - 4-8 frasi concise in italiano\n"
            "   - Forma discorsiva (no elenchi puntati, no bullet points)\n"
            "   - Tono diretto e informativo\n"
            "   - Non citare 'secondo la fonte X' (è implicito)\n"
            "\n"
            "5. **SE DAVVERO MANCANO INFO**:\n"
            "   - Descrivi cosa c'È invece di cosa manca\n"
            "   - Esempio: 'Le fonti parlano di [tema generale] e menzionano [dettagli A, B]. "
            "Per dati specifici su [C] servirebbe cercare [suggerimento mirato]'\n"
            "   - Mai solo 'non c'è abbastanza' senza dare nulla\n"
            "\n"
            "6. **VERIFICA FINALE**:\n"
            "   - La tua risposta contiene almeno 3 facts concreti? ✓\n"
            "   - Hai evitato tutte le frasi vietate? ✓\n"
            "   - L'utente ottiene valore anche senza aprire le fonti? ✓\n"
            "\n"
            "RISPONDI ORA in italiano seguendo le regole:"
        )

        try:
            summary = await reply_with_llm(
                user_prompt,
                persona
                or (
                    "Sei una GPT neutra, modulare e molto precisa: segui rigorosamente "
                    "le regole fornite nel prompt dell'utente."
                ),
            )
        except Exception:
            summary = ""
            note = "llm_summary_failed"

        # === ⭐ VALIDATION POST-SYNTHESIS (NUOVO) ⭐ ===
        if summary:
            try:
                from core.synthesis_validator import get_synthesis_validator

                validator = get_synthesis_validator()
                validation_result = validator.validate(summary)

                if not validation_result["valid"]:
                    log.warning(
                        "Synthesis quality low: score=%.2f, issues=%s",
                        validation_result["score"],
                        validation_result["issues"],
                    )

                    # Se troppo basso, aggiungi disclaimer
                    if validation_result["score"] < 0.5:
                        summary += (
                            "\n\n[Nota: Questa sintesi potrebbe essere incompleta. "
                            "Consultare le fonti per dettagli completi.]"
                        )

                # Log metriche
                log.info(
                    "Synthesis quality: score=%.2f, facts=%d, length=%d",
                    validation_result["score"],
                    validation_result["facts_count"],
                    validation_result["length"],
                )

            except Exception as e:
                log.warning(f"Synthesis validation failed: {e}")

        # Fallback se summary vuota o nulla
        answer_text = (summary or "").strip()
        if not answer_text:
            answer_text = (
                "Non sono riuscito a generare una sintesi strutturata a partire dagli estratti "
                "disponibili, ma le fonti collegate includono contenuti rilevanti che "
                "approfondiscono l'argomento."
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
            "note": note,
        }
