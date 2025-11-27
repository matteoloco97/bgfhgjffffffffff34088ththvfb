# agents/advanced_web_research.py
"""
Advanced multi-step web research agent.
Simile a Claude: iterazioni multiple per coverage completo.
"""

import asyncio
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

log = logging.getLogger(__name__)

@dataclass
class ResearchStep:
    step_num: int
    query: str
    reason: str
    sources_found: int
    quality_score: float


class AdvancedWebResearch:
    """
    Multi-step web research con reasoning iterativo.
    Continua a cercare finché non ha info sufficienti.
    """
    
    def __init__(
        self, 
        max_steps: int = 3,
        min_sources: int = 8,
        quality_threshold: float = 0.70
    ):
        self.max_steps = max_steps
        self.min_sources = min_sources
        self.quality_threshold = quality_threshold
    
    async def research_deep(
        self, 
        original_query: str,
        persona: str = ""
    ) -> Dict[str, Any]:
        """
        Ricerca profonda multi-step.
        
        Strategia:
        1. Query iniziale → ottieni prime fonti
        2. Analizza gaps informativi
        3. Genera follow-up queries per colmare gaps
        4. Continua fino a coverage completo o max_steps
        """
        # CRITICAL: Import con fallback Core/core
        web_search = None
        try:
            from Core.web_search import search as web_search
            log.info("✓ Imported web_search from Core.web_search")
        except ImportError:
            try:
                from core.web_search import search as web_search
                log.info("✓ Imported web_search from core.web_search")
            except ImportError:
                log.error("✗ Cannot import web_search module")
                return {
                    "answer": "Errore: modulo di ricerca web non disponibile.",
                    "sources": [],
                    "total_sources": 0,
                    "steps": [],
                    "quality_final": 0.0
                }
        
        try:
            from core.web_tools import fetch_and_extract_robust
            from core.chat_engine import reply_with_llm
            from core.token_budget import trim_to_tokens
        except ImportError as e:
            log.error(f"✗ Import error: {e}")
            return {
                "answer": f"Errore import: {e}",
                "sources": [],
                "total_sources": 0,
                "steps": [],
                "quality_final": 0.0
            }
        
        all_sources: List[Dict[str, Any]] = []
        all_extracts: List[Dict[str, Any]] = []
        steps: List[ResearchStep] = []
        
        current_query = original_query
        
        for step_num in range(1, self.max_steps + 1):
            log.info(f"🔍 STEP {step_num}: {current_query}")
            
            # 1. SERP search
            try:
                serp_results = web_search(current_query, num=12)
                log.info(f"SERP returned {len(serp_results) if serp_results else 0} results")
            except Exception as e:
                log.error(f"Search failed: {e}")
                serp_results = []
            
            if not serp_results:
                log.warning(f"No results for step {step_num}")
                break
            
            # 2. Filter già visti
            new_results = [
                r for r in serp_results 
                if r.get('url') and r['url'] not in {s.get('url') for s in all_sources}
            ]
            
            log.info(f"Found {len(new_results)} new sources (total: {len(all_sources) + len(new_results)})")
            
            # 3. Fetch parallel (top 4 nuovi per step)
            fetch_tasks = [
                self._fetch_one(r, idx) 
                for idx, r in enumerate(new_results[:4])
            ]
            
            try:
                new_extracts = await asyncio.gather(*fetch_tasks, return_exceptions=True)
                new_extracts = [e for e in new_extracts if isinstance(e, dict) and e.get('text')]
            except Exception as e:
                log.error(f"Fetch error: {e}")
                new_extracts = []
            
            all_sources.extend(new_results[:4])
            all_extracts.extend(new_extracts)
            
            log.info(f"Step {step_num}: fetched {len(new_extracts)} extracts, total extracts: {len(all_extracts)}")
            
            # 4. Valuta qualità info raccolte
            quality_score = self._assess_quality(all_extracts, original_query)
            
            steps.append(ResearchStep(
                step_num=step_num,
                query=current_query,
                reason="initial_query" if step_num == 1 else "follow_up",
                sources_found=len(new_results),
                quality_score=quality_score
            ))
            
            # 5. Stopping conditions
            if len(all_sources) >= self.min_sources and quality_score >= self.quality_threshold:
                log.info(f"✅ Sufficient info: {len(all_sources)} sources, quality {quality_score:.2f}")
                break
            
            if step_num >= self.max_steps:
                log.info(f"⏹️ Max steps reached")
                break
            
            # 6. Genera follow-up query intelligente (solo se serve)
            if len(all_extracts) < 3:
                log.info("Not enough extracts for follow-up, stopping")
                break
            
            # Salto follow-up per ora - troppo complesso
            # next_query = await self._generate_followup(...)
            break  # TEMP: solo 1 step per debug
        
        # 7. Synthesis
        if not all_extracts:
            return {
                "answer": "Nessuna informazione trovata nelle fonti disponibili.",
                "sources": [{"url": s.get('url', ''), "title": s.get('title', '')} for s in all_sources],
                "total_sources": len(all_sources),
                "steps": [
                    {
                        "step": s.step_num,
                        "query": s.query,
                        "sources_found": s.sources_found,
                        "quality": round(s.quality_score, 3)
                    }
                    for s in steps
                ],
                "quality_final": 0.0
            }
        
        final_answer = await self._hierarchical_synthesis(
            original_query,
            all_extracts,
            persona
        )
        
        return {
            "answer": final_answer,
            "sources": [{"url": s.get('url', ''), "title": s.get('title', '')} for s in all_sources],
            "total_sources": len(all_sources),
            "steps": [
                {
                    "step": s.step_num,
                    "query": s.query,
                    "sources_found": s.sources_found,
                    "quality": round(s.quality_score, 3)
                }
                for s in steps
            ],
            "quality_final": self._assess_quality(all_extracts, original_query)
        }
    
    async def _fetch_one(self, result: Dict, idx: int) -> Dict[str, Any]:
        """Fetch singola fonte con robust extraction."""
        try:
            from core.web_tools import fetch_and_extract_robust
            from core.token_budget import trim_to_tokens
        except ImportError as e:
            log.error(f"Import error in _fetch_one: {e}")
            return {}
        
        url = result.get('url', '')
        if not url:
            return {}
        
        try:
            text, og_img = await asyncio.wait_for(
                fetch_and_extract_robust(url, timeout=6.0),
                timeout=8.0
            )
            
            if text and len(text) > 100:
                return {
                    "url": url,
                    "title": result.get('title', url),
                    "text": trim_to_tokens(text, 800),
                    "og_image": og_img,
                    "index": idx
                }
        except Exception as e:
            log.warning(f"Fetch failed {url}: {e}")
        
        return {}
    
    def _assess_quality(self, extracts: List[Dict], query: str) -> float:
        """
        Valuta qualità info raccolte (0-1).
        
        Metriche:
        - Coverage: quanti extract menzionano keywords della query
        - Depth: lunghezza media estratti
        - Diversity: varietà domini
        """
        if not extracts:
            return 0.0
        
        query_terms = set(query.lower().split())
        
        coverage_scores = []
        for ex in extracts:
            text = ex.get('text', '').lower()
            matches = sum(1 for term in query_terms if term in text and len(term) > 3)
            coverage_scores.append(matches / max(1, len(query_terms)))
        
        avg_coverage = sum(coverage_scores) / len(coverage_scores) if coverage_scores else 0.0
        
        avg_length = sum(len(ex.get('text', '')) for ex in extracts) / len(extracts)
        depth_score = min(1.0, avg_length / 2000)
        
        unique_domains = len(set(
            ex.get('url', '').split('/')[2] if '/' in ex.get('url', '') else ''
            for ex in extracts if ex.get('url')
        ))
        diversity_score = min(1.0, unique_domains / 4)
        
        # Weighted combination
        quality = (
            avg_coverage * 0.5 +
            depth_score * 0.3 +
            diversity_score * 0.2
        )
        
        return round(quality, 3)
    
    async def _hierarchical_synthesis(
        self,
        query: str,
        extracts: List[Dict],
        persona: str
    ) -> str:
        """
        Sintesi gerarchica per gestire molte fonti (10-20+).
        
        Per ora: sintesi diretta semplice.
        TODO: implementare chunking per 10+ fonti
        """
        try:
            from core.chat_engine import reply_with_llm
            from core.token_budget import trim_to_tokens
        except ImportError as e:
            log.error(f"Import error in synthesis: {e}")
            return "Errore nella sintesi."
        
        if not extracts:
            return "Nessuna informazione trovata."
        
        # Direct synthesis (max 5 fonti)
        ctx = "\n\n".join([
            f"### {e.get('title', '')}\nURL: {e.get('url', '')}\n\n{e.get('text', '')}"
            for e in extracts[:5]
        ])
        ctx = trim_to_tokens(ctx, 2000)
        
        prompt = f"""
Sintetizza le seguenti fonti per rispondere alla query.

FONTI WEB:
{ctx}

QUERY: {query}

REGOLE:
- Fornisci una risposta completa e concreta
- Usa 5-8 frasi
- Includi tutti i fatti rilevanti dalle fonti
- NO elenchi puntati
- Se le fonti non rispondono completamente, specifica cosa manca

RISPOSTA:
"""
        
        try:
            return await reply_with_llm(prompt, persona)
        except Exception as e:
            log.error(f"LLM synthesis failed: {e}")
            return "Errore nella generazione della sintesi."


# Singleton
_INSTANCE: Optional[AdvancedWebResearch] = None

def get_advanced_research() -> AdvancedWebResearch:
    """Get singleton instance."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = AdvancedWebResearch(
            max_steps=3,
            min_sources=8,
            quality_threshold=0.70
        )
    return _INSTANCE
