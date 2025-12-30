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
#
# ENHANCEMENT v3 (2024):
# - Integrated smart synthesis for better content extraction
# - Better quality scoring and sentence extraction

from __future__ import annotations

import os
import time
import asyncio
import logging
import hashlib
from typing import Any, Dict, List, Optional, Set
from urllib.parse import urlparse

from core.web_tools import fetch_and_extract, fetch_and_extract_async, parallel_fetch_urls
from core.chat_engine import reply_with_llm

log = logging.getLogger(__name__)

# Import SearchEngine for multi-provider search with fallback
try:
    from core.search_engine import get_search_engine, SearchEngine
    _search_engine = get_search_engine()
except Exception:
    _search_engine = None  # type: ignore

# Legacy fallback to old web_search if SearchEngine is not available
try:
    from core.web_search import search as web_search_async
except Exception:
    web_search_async = None  # type: ignore

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


# === CONFIGURAZIONE OTTIMIZZATA PER RICERCA INTELLIGENTE ===
WEB_RESEARCH_BUDGET_TOK = int(os.getenv("WEB_RESEARCH_BUDGET_TOK", "4000"))
WEB_RESEARCH_FETCH_TIMEOUT_S = float(os.getenv("WEB_RESEARCH_FETCH_TIMEOUT_S", "8.0"))
WEB_RESEARCH_MAX_DOCS = int(os.getenv("WEB_RESEARCH_MAX_DOCS", "8"))
WEB_RESEARCH_MAX_STEPS = int(os.getenv("WEB_RESEARCH_MAX_STEPS", "4"))
WEB_RESEARCH_QUALITY_THRESHOLD = float(os.getenv("WEB_RESEARCH_QUALITY_THRESHOLD", "0.55"))
WEB_RESEARCH_MAX_CONCURRENT = int(os.getenv("WEB_RESEARCH_MAX_CONCURRENT", "6"))
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
        """Scarica una singola pagina usando fetch_and_extract_async."""
        url = item.get("url") or ""
        if not url:
            return None

        try:
            # Use the new async version with built-in timeout and retries
            text, _ = await fetch_and_extract_async(url, timeout=WEB_RESEARCH_FETCH_TIMEOUT_S)
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
        self, items: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Scarica più documenti in parallelo con rate limiting.
        
        ENHANCEMENT: Now uses smart synthesis for better content extraction.
        """
        if not items:
            return []

        # Limita concorrenza
        semaphore = asyncio.Semaphore(self.max_concurrent)

        async def fetch_with_semaphore(item):
            async with semaphore:
                return await self._fetch_one(item)

        tasks = [fetch_with_semaphore(item) for item in items]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        docs = []
        for r in results:
            if isinstance(r, dict) and r:
                docs.append(r)
            elif isinstance(r, Exception):
                log.debug(f"Fetch error: {r}")

        # ENHANCEMENT: Use smart synthesis to improve content quality
        try:
            from core.smart_synthesis import get_smart_synthesizer
            synthesizer = get_smart_synthesizer()
            
            # Extract better text snippets from each doc
            for doc in docs:
                text = doc.get("text", "")
                if text and len(text) > 200:
                    # Extract key sentences for better quality
                    key_sentences = synthesizer.extract_key_sentences(
                        text, 
                        query="",  # No specific query, just best sentences
                        top_n=3
                    )
                    if key_sentences:
                        # Replace text with key sentences for better synthesis
                        doc["text"] = " ".join(key_sentences)
        except Exception as e:
            log.debug(f"Smart synthesis enhancement failed: {e}")

        return docs

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

        # Check for available search capability
        if not _search_engine and not web_search_async:
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

            # STEP N: ricerca SERP - Use SearchEngine with multi-provider fallback
            results = []
            try:
                if _search_engine:
                    # Use new SearchEngine with multi-provider and multilingual support
                    search_result = await _search_engine.search(current_query)
                    # Convert SearchResult objects to dict format
                    results = [
                        {
                            "url": r.url,
                            "title": r.title,
                            "snippet": r.snippet,
                            "domain": r.domain,
                            "score": r.score,
                        }
                        for r in search_result.results
                    ]
                    # Log diagnostic info
                    if search_result.fallback_triggered:
                        log.info(
                            f"SearchEngine fallback: providers_tried={search_result.providers_tried}"
                        )
                elif web_search_async:
                    # Legacy fallback to old web_search
                    results = await web_search_async(current_query, num=10) or []
            except Exception as e:
                # Truncate query in log to avoid logging sensitive data
                log.warning(f"Web search failed: {e}")
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

        # === Prompt finale V4 - ANTI-HALLUCINATION (grounded response) ===
        user_prompt = (
            "CONTESTO: Sei un assistente che risponde ESCLUSIVAMENTE basandosi sui dati forniti.\n"
            "\n"
            "=== REGOLA FONDAMENTALE ===\n"
            "NON INVENTARE MAI dati, numeri, date, prezzi o fatti non presenti negli estratti.\n"
            "Se un'informazione NON è negli estratti, NON la citare.\n"
            "\n"
            "HAI A DISPOSIZIONE questi estratti da pagine web:\n"
            f"{ctx}\n"
            "\n"
            "DOMANDA UTENTE:\n"
            f"{query}\n"
            "\n"
            "=== REGOLE CRITICHE ===\n"
            "\n"
            "1. **USA SOLO I DATI PRESENTI NEGLI ESTRATTI**:\n"
            "   - Cita SOLO numeri, date, prezzi che sono ESPLICITAMENTE scritti negli estratti\n"
            "   - Se un dato non è presente, NON inventarlo\n"
            "   - Preferisci dire 'gli estratti non riportano questo dato' piuttosto che inventare\n"
            "\n"
            "2. **COSA FARE SE I DATI SONO PARZIALI**:\n"
            "   - Riporta TUTTO quello che trovi effettivamente negli estratti\n"
            "   - Se trovi informazioni correlate ma non esattamente ciò che è stato chiesto, riportale\n"
            "   - Indica chiaramente cosa è presente e cosa manca\n"
            "\n"
            "3. **FORMATO RISPOSTA**:\n"
            "\n"
            "   📌 **[Titolo argomento]**\n"
            "\n"
            "   **✅ Informazioni dalle fonti:**\n"
            "   • [Solo fatti trovati negli estratti - con numeri esatti se presenti]\n"
            "   • [Altro fatto presente]\n"
            "\n"
            "   **⚠️ Nota:** [Se mancano dati specifici, indicalo qui onestamente]\n"
            "\n"
            "4. **SE GLI ESTRATTI NON CONTENGONO INFO RILEVANTI**:\n"
            "   Rispondi così:\n"
            "   📌 **Ricerca Web**\n"
            "   \n"
            "   Gli estratti disponibili non contengono informazioni specifiche su [argomento richiesto].\n"
            "   \n"
            "   **Contenuti trovati:** [descrivi brevemente cosa c'è nelle fonti]\n"
            "\n"
            "5. **VERIFICA FINALE PRIMA DI RISPONDERE**:\n"
            "   - Ho citato SOLO dati presenti negli estratti? ✓\n"
            "   - Ho evitato di inventare numeri/date/prezzi? ✓\n"
            "   - Ho indicato chiaramente se mancano informazioni? ✓\n"
            "\n"
            "RISPONDI ORA in italiano:"
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
