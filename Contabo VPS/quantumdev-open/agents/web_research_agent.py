# agents/web_research_agent.py — WebResearchAgent (versione MULTI-STEP AGGRESSIVA v2)
# Obiettivo: dare SEMPRE una risposta utile e concreta, usando SOLO ciò che è negli estratti.
#
# FEATURES v2:
# - Multi-step research: se la prima ricerca non è sufficiente, riformula e cerca di nuovo
# - Parallel fetch aggressivo con asyncio.gather
# - Dedup & diversità: evita fonti duplicate o troppo simili
# - Prompt di sintesi strutturato con blocchi ✅/⚠️
# - Vietato limitarsi a dire "le fonti non contengono..." se esistono info utili
# - Niente "apri la fonte" come unica soluzione: la risposta deve essere autosufficiente

from __future__ import annotations

import os
import time
import asyncio
import logging
import hashlib
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

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


# === CONFIGURAZIONE ===
WEB_RESEARCH_BUDGET_TOK = int(os.getenv("WEB_RESEARCH_BUDGET_TOK", "2000"))
WEB_RESEARCH_FETCH_TIMEOUT_S = float(os.getenv("WEB_RESEARCH_FETCH_TIMEOUT_S", "5.0"))
WEB_RESEARCH_MAX_DOCS = int(os.getenv("WEB_RESEARCH_MAX_DOCS", "5"))
WEB_RESEARCH_MAX_STEPS = int(os.getenv("WEB_RESEARCH_MAX_STEPS", "3"))
WEB_RESEARCH_QUALITY_THRESHOLD = float(os.getenv("WEB_RESEARCH_QUALITY_THRESHOLD", "0.6"))
WEB_RESEARCH_MAX_CONCURRENT = int(os.getenv("WEB_RESEARCH_MAX_CONCURRENT", "4"))
WEB_RESEARCH_MIN_KEYWORD_LEN = int(os.getenv("WEB_RESEARCH_MIN_KEYWORD_LEN", "3"))


class WebResearchAgent:
    """
    Orchestratore di ricerca web multi-step (versione aggressiva v2).

    FEATURES:
    - Multi-step: se la prima ricerca non basta, riformula e cerca ancora
    - Parallel fetch: scarica più pagine in parallelo
    - Dedup: evita fonti duplicate per dominio
    - Sintesi strutturata con blocchi ✅/⚠️

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
        self.max_steps = max(1, WEB_RESEARCH_MAX_STEPS)
        self.max_concurrent = max(1, WEB_RESEARCH_MAX_CONCURRENT)
        self.seen_urls: Set[str] = set()
        self.seen_domains: Dict[str, int] = {}

    def _get_domain(self, url: str) -> str:
        """Estrae dominio da URL."""
        try:
            host = urlparse(url).hostname or ""
            parts = host.split(".")
            return ".".join(parts[-2:]) if len(parts) >= 2 else host
        except Exception:
            return ""

    def _deduplicate_results(
        self, results: List[Dict[str, Any]], max_per_domain: int = 2
    ) -> List[Dict[str, Any]]:
        """
        Rimuove duplicati e limita risultati per dominio.
        Garantisce diversità delle fonti.
        """
        deduped: List[Dict[str, Any]] = []
        domain_count: Dict[str, int] = {}

        for r in results:
            url = r.get("url", "")
            if not url or url in self.seen_urls:
                continue

            domain = self._get_domain(url)
            if domain_count.get(domain, 0) >= max_per_domain:
                continue

            self.seen_urls.add(url)
            domain_count[domain] = domain_count.get(domain, 0) + 1
            deduped.append(r)

        return deduped

    async def _fetch_one(self, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Scarica una singola pagina."""
        url = item.get("url") or ""
        if not url:
            return None

        try:
            text, _ = await asyncio.wait_for(
                fetch_and_extract(url),
                timeout=WEB_RESEARCH_FETCH_TIMEOUT_S,
            )
        except asyncio.TimeoutError:
            log.debug(f"Timeout fetching {url}")
            return None
        except Exception as e:
            log.debug(f"Error fetching {url}: {e}")
            return None

        if not text or len(text) < 100:
            return None

        trimmed = trim_to_tokens(
            text, WEB_RESEARCH_BUDGET_TOK // self.max_docs
        )
        return {
            "url": url,
            "title": item.get("title") or url,
            "text": trimmed,
            "domain": self._get_domain(url),
        }

    async def _fetch_docs_parallel(
        self, results: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Fetch parallelo con limite di concorrenza.
        Usa asyncio.Semaphore per limitare richieste simultanee.
        """
        sem = asyncio.Semaphore(self.max_concurrent)
        extracts: List[Dict[str, Any]] = []

        async def _bounded_fetch(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
            async with sem:
                return await self._fetch_one(item)

        tasks = [
            asyncio.create_task(_bounded_fetch(r))
            for r in results[:self.max_docs]
        ]

        done = await asyncio.gather(*tasks, return_exceptions=True)

        for d in done:
            if isinstance(d, dict) and d.get("text"):
                extracts.append(d)

        return extracts

    def _estimate_quality(self, extracts: List[Dict[str, Any]], query: str) -> float:
        """
        Stima qualità degli estratti rispetto alla query.
        Score 0-1 basato su:
        - Numero di estratti
        - Diversità domini
        - Presenza keywords query negli estratti
        """
        if not extracts:
            return 0.0

        # Numero estratti (più è meglio, max 5)
        count_score = min(len(extracts) / 5.0, 1.0)

        # Diversità domini
        domains = set(e.get("domain", "") for e in extracts)
        diversity_score = min(len(domains) / 3.0, 1.0)

        # Keyword match
        query_words = set(query.lower().split())
        keyword_hits = 0
        for e in extracts:
            text_lower = (e.get("text") or "").lower()
            for word in query_words:
                if len(word) > WEB_RESEARCH_MIN_KEYWORD_LEN and word in text_lower:
                    keyword_hits += 1
        
        # Evita divisione per zero e calcola score
        max_possible_hits = max(len(query_words), 1) * max(len(extracts), 1)
        keyword_score = min(keyword_hits / max_possible_hits, 1.0)

        # Media pesata
        return 0.4 * count_score + 0.3 * diversity_score + 0.3 * keyword_score

    def _generate_followup_query(self, original_query: str, step: int) -> str:
        """
        Genera query di follow-up per step successivi.
        Aggiunge termini più specifici.
        """
        suffixes = [
            " guida completa",
            " spiegazione dettagliata",
            " esempi pratici",
            " aggiornamento recente",
        ]
        idx = (step - 1) % len(suffixes)
        return original_query + suffixes[idx]

    async def research(self, query: str, persona: str) -> Dict[str, Any]:
        t0 = time.perf_counter()
        steps: List[Dict[str, Any]] = []
        note: str = "ok"
        all_extracts: List[Dict[str, Any]] = []
        all_sources: List[Dict[str, str]] = []

        # Reset stato per nuova ricerca
        self.seen_urls = set()
        self.seen_domains = {}

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

        # === MULTI-STEP RESEARCH ===
        current_query = query
        best_quality = 0.0

        for step_num in range(1, self.max_steps + 1):
            step_start = time.perf_counter()

            # STEP N: ricerca SERP
            try:
                results = web_search_simple(current_query, num=10) or []
            except Exception:
                results = []

            # Deduplica risultati
            results = self._deduplicate_results(results)

            step_info = {
                "step": step_num,
                "query": current_query,
                "results_count": len(results),
                "docs_read": 0,
                "novelty": 0.0,
            }

            if not results:
                steps.append(step_info)
                if step_num == 1:
                    # Prima ricerca vuota: prova con query modificata
                    current_query = self._generate_followup_query(query, step_num)
                    continue
                break

            # Fetch parallelo
            extracts = await self._fetch_docs_parallel(results)
            step_info["docs_read"] = len(extracts)

            # Calcola qualità
            quality = self._estimate_quality(extracts, query)
            step_info["quality"] = round(quality, 3)
            step_info["elapsed_ms"] = int((time.perf_counter() - step_start) * 1000)

            # Aggiungi estratti non duplicati
            for e in extracts:
                if e.get("url") not in [s.get("url") for s in all_sources]:
                    all_extracts.append(e)
                    all_sources.append({"url": e["url"], "title": e["title"]})

            steps.append(step_info)

            # Se qualità sufficiente o miglioramento minimo, stop
            if quality >= WEB_RESEARCH_QUALITY_THRESHOLD:
                log.info(f"Quality threshold reached at step {step_num}: {quality:.2f}")
                break

            improvement = quality - best_quality
            if improvement < 0.1 and step_num > 1:
                log.info(f"Minimal improvement at step {step_num}, stopping")
                break

            best_quality = max(best_quality, quality)

            # Genera query per step successivo
            if step_num < self.max_steps:
                current_query = self._generate_followup_query(query, step_num + 1)

        # Se nessun estratto dopo tutti gli step
        if not all_extracts:
            srcs = all_sources[:3] if all_sources else []
            return {
                "answer": (
                    "Ho individuato alcune pagine potenzialmente rilevanti, ma non sono riuscito "
                    "a estrarne il contenuto in modo affidabile. "
                    "Prova a riformulare la domanda con più dettagli specifici."
                ),
                "sources": srcs,
                "steps": steps,
                "total_steps": len(steps),
                "note": "no_extracts",
            }

        # Costruisci contesto
        ctx_parts: List[str] = []
        for i, e in enumerate(all_extracts[:self.max_docs], 1):
            ctx_parts.append(
                f"### Fonte {i}: {e['title']}\nURL: {e['url']}\n\n{e['text']}"
            )

        ctx = "\n\n".join(ctx_parts)
        ctx = trim_to_tokens(ctx, WEB_RESEARCH_BUDGET_TOK)

        # === Prompt finale ULTRA-AGGRESSIVO V3 (con formato standardizzato) ===
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
            "4. **FORMATO RISPOSTA STANDARDIZZATO**:\n"
            "   Usa ESATTAMENTE questo formato:\n"
            "\n"
            "   📌 **[Titolo breve argomento]**\n"
            "\n"
            "   **✅ Dati verificati:**\n"
            "   • [Fatto 1 con numeri/date se presenti]\n"
            "   • [Fatto 2]\n"
            "   • [Fatto 3]\n"
            "\n"
            "   **⚠️ Analisi/Interpretazione:**\n"
            "   [1-2 frasi con considerazioni, trend, o cosa significano i dati]\n"
            "\n"
            "5. **SE DAVVERO MANCANO INFO**:\n"
            "   - Descrivi cosa c'È invece di cosa manca\n"
            "   - Esempio: 'Le fonti parlano di [tema generale] e menzionano [dettagli A, B].'\n"
            "   - Mai solo 'non c'è abbastanza' senza dare nulla\n"
            "\n"
            "6. **VERIFICA FINALE**:\n"
            "   - La risposta contiene almeno 3 facts concreti? ✓\n"
            "   - Hai usato i blocchi ✅ e ⚠️? ✓\n"
            "   - L'utente ottiene valore senza aprire le fonti? ✓\n"
            "\n"
            "RISPONDI ORA in italiano seguendo il formato:"
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

        # === ⭐ VALIDATION POST-SYNTHESIS ⭐ ===
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
                "📌 **Ricerca Web**\n\n"
                "**⚠️ Nota:**\n"
                "Non sono riuscito a generare una sintesi strutturata a partire dagli estratti "
                "disponibili, ma le fonti collegate includono contenuti rilevanti che "
                "approfondiscono l'argomento."
            )

        total_steps = len(steps)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)

        # Aggiungi step finale con metriche
        steps.append(
            {
                "step": total_steps + 1,
                "type": "synthesis",
                "docs_used": len(all_extracts),
                "elapsed_ms": elapsed_ms,
            }
        )

        return {
            "answer": answer_text,
            "sources": all_sources[:self.max_docs],
            "steps": steps,
            "total_steps": len(steps),
            "note": note,
        }
