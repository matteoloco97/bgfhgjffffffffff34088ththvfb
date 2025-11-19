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
                "answer": "Il motore di ricerca interno non è configurato, quindi non posso eseguire la ricerca sul web.",
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
                    "Non ho trovato risultati affidabili collegati alla tua richiesta nei motori di ricerca utilizzati. "
                    "Se puoi, prova a riformulare indicando più dettagli (ad esempio data, luogo, competizione, sito di riferimento "
                    "o il contesto specifico) così la ricerca può essere più mirata."
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
                    "Ho individuato alcune pagine potenzialmente rilevanti, ma non sono riuscito a estrarne il contenuto "
                    "in modo affidabile (timeout o errore di lettura). Le URL che ho trovato possono comunque contenere "
                    "informazioni utili sull'argomento."
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

        # Prompt finale AGGRESSIVO: risposta obbligatoria, concreta, in italiano + fonti
        user_prompt = (
            "RUOLO: stai facendo una ricerca sul web per rispondere alla DOMANDA qui sotto.\n"
            "Hai a disposizione estratti da più pagine web (titolo, URL e contenuto testuale).\n"
            "\n"
            "OBIETTIVO: fornire una risposta chiara, utile e CONCRETA in ITALIANO basandoti SOLO su ciò che compare negli estratti.\n"
            "\n"
            "REGOLE CRITICHE (DA SEGUIRE ALLA LETTERA):\n"
            "1) Rispondi SEMPRE in italiano, in forma discorsiva, in 3–8 frasi massimo.\n"
            "2) Usa ESCLUSIVAMENTE le informazioni presenti negli estratti: non aggiungere fatti, numeri o dettagli che non compaiono "
            "nei testi (niente conoscenza esterna, niente supposizioni).\n"
            "3) Se trovi numeri (prezzi, date, percentuali, quantità, valori di mercato, orari ecc.), riportali con chiarezza e specifica l'unità.\n"
            "4) Se le fonti NON contengono il numero preciso o il dettaglio esatto che la domanda chiede:\n"
            "   - spiega comunque cosa dicono le fonti sull'argomento,\n"
            "   - riassumi i punti principali realmente presenti negli estratti,\n"
            "   - indica in modo esplicito quali informazioni mancano o non sono specificate.\n"
            "   NON è ammesso limitarsi a dire che 'le fonti non contengono l'informazione': devi comunque sintetizzare ciò che c'è.\n"
            "5) Se le fonti sono parzialmente discordanti, descrivi brevemente le differenze (es. valori leggermente diversi, interpretazioni alternative) "
            "e, se possibile, segnala in modo neutro quale fonte sembra più autorevole (es. sito ufficiale vs blog).\n"
            "6) Evita frasi vaghe e generiche; sii specifico e pratico. Evita anche frasi del tipo 'apri il link' o 'consulta direttamente la fonte' "
            "come unica soluzione: la tua risposta deve essere autosufficiente.\n"
            "7) Alla fine della risposta aggiungi SEMPRE una riga finale con il formato:\n"
            "   'Fonti: URL1, URL2, URL3'\n"
            "   usando al massimo 3 URL tra le più rilevanti e senza ulteriori commenti in quella riga.\n"
            "\n"
            "Se gli estratti non rispondono in modo diretto alla domanda, spiega cosa contengono comunque (ad esempio: 'parlano di contesto generale, "
            "ma non forniscono il dato X richiesto'), mantenendo però la risposta utile e leggibile.\n"
            "\n"
            f"DOMANDA: {query}\n\n"
            "=== ESTRATTI DAL WEB (usa SOLO queste informazioni per rispondere) ===\n"
            f"{ctx}\n"
        )

        try:
            answer_text = await reply_with_llm(
                user_prompt,
                persona or "Sei una GPT neutra, modulare e molto precisa: segui rigorosamente le regole fornite nel prompt dell'utente."
            )
        except Exception:
            # fallback minimalista ma comunque utile (senza invito diretto ad 'aprire i link')
            answer_text = (
                "Ho riscontrato un problema nel generare una sintesi automatica a partire dagli estratti disponibili. "
                "Le fonti associate contengono comunque informazioni potenzialmente utili sull'argomento."
            )

        answer_text = (answer_text or "").strip()
        if not answer_text:
            answer_text = (
                "Non sono riuscito a generare una risposta strutturata a partire dagli estratti disponibili, "
                "ma le fonti collegate includono contenuti rilevanti che approfondiscono l'argomento."
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
