#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/enhanced_web_engine.py — Enhanced Web Engine (ChatGPT/Claude Parity)

Unified web engine that combines all enhanced components:
- Multi-step reasoning for complex queries
- Inline citations (Claude-style)
- Credibility scoring for sources
- Follow-up question generation
- Semantic source deduplication

This module provides the main entry point for web-powered responses
matching ChatGPT/Claude quality.

Author: QuantumDev Enhancement
Version: 1.0.0
"""

from __future__ import annotations

import os
import re
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


# === Configuration ===
def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (ValueError, TypeError):
        return default


# Configuration
ENHANCED_WEB_ENABLED = _env_bool("ENHANCED_WEB_ENABLED", True)
MULTI_STEP_REASONING_ENABLED = _env_bool("MULTI_STEP_REASONING_ENABLED", True)
INLINE_CITATIONS_ENABLED = _env_bool("INLINE_CITATIONS_ENABLED", True)
CREDIBILITY_SCORING_ENABLED = _env_bool("CREDIBILITY_SCORING_ENABLED", True)
FOLLOWUP_SUGGESTIONS_ENABLED = _env_bool("FOLLOWUP_SUGGESTIONS_ENABLED", True)
MIN_CREDIBILITY_SCORE = _env_float("MIN_CREDIBILITY_SCORE", 0.4)
MAX_SOURCES_PER_RESPONSE = _env_int("MAX_SOURCES_PER_RESPONSE", 5)


@dataclass
class EnhancedWebResponse:
    """Response from enhanced web engine."""
    text: str
    sources: List[Dict[str, Any]] = field(default_factory=list)
    citations_text: str = ""
    followup_questions: List[str] = field(default_factory=list)
    reasoning_trace: List[str] = field(default_factory=list)
    confidence: float = 0.0
    search_triggered: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


class EnhancedWebEngine:
    """
    Enhanced Web Engine for ChatGPT/Claude-quality responses.
    
    Integrates:
    - Multi-step reasoning for complex queries
    - Source credibility assessment
    - Inline citation formatting
    - Follow-up question generation
    - Semantic source deduplication
    """
    
    def __init__(
        self,
        llm_func=None,
        search_func=None
    ):
        """
        Initialize enhanced web engine.
        
        Args:
            llm_func: Async LLM function (user_text, persona) -> str
            search_func: Async search function (query, num) -> List[Dict]
        """
        self.llm_func = llm_func
        self.search_func = search_func
        
        # Lazy-load components
        self._reasoner = None
        self._citation_formatter = None
        self._credibility_scorer = None
        self._followup_generator = None
    
    @property
    def reasoner(self):
        """Lazy-load multi-step reasoner."""
        if self._reasoner is None:
            from core.multi_step_reasoning import get_multi_step_reasoner
            self._reasoner = get_multi_step_reasoner(
                llm_func=self.llm_func,
                search_func=self.search_func
            )
        return self._reasoner
    
    @property
    def citation_formatter(self):
        """Lazy-load citation formatter."""
        if self._citation_formatter is None:
            from core.citation_formatter import get_citation_formatter
            self._citation_formatter = get_citation_formatter()
        return self._citation_formatter
    
    @property
    def credibility_scorer(self):
        """Lazy-load credibility scorer."""
        if self._credibility_scorer is None:
            from core.credibility_scoring import get_credibility_scorer
            self._credibility_scorer = get_credibility_scorer()
        return self._credibility_scorer
    
    @property
    def followup_generator(self):
        """Lazy-load follow-up generator."""
        if self._followup_generator is None:
            from core.followup_generator import get_followup_generator
            self._followup_generator = get_followup_generator(llm_func=self.llm_func)
        return self._followup_generator
    
    async def process_query(
        self,
        query: str,
        persona: str = "",
        context: Optional[Dict[str, Any]] = None,
        enable_citations: bool = True,
        enable_followups: bool = True
    ) -> EnhancedWebResponse:
        """
        Process a query with all enhanced features.
        
        Args:
            query: User query
            persona: System persona for LLM
            context: Additional context
            enable_citations: Enable inline citations
            enable_followups: Enable follow-up suggestions
            
        Returns:
            EnhancedWebResponse with full results
        """
        if not ENHANCED_WEB_ENABLED:
            # Fallback to basic processing
            return await self._basic_process(query, persona)
        
        context = context or {}
        result = EnhancedWebResponse(text="", confidence=0.0)
        
        try:
            # Step 1: Analyze query complexity
            log.info(f"[ENHANCED-WEB] Processing query: {query[:80]}...")
            
            complexity_score, needs_multistep = await self._analyze_complexity(query)
            result.metadata['complexity_score'] = complexity_score
            result.metadata['multi_step'] = needs_multistep
            
            # Step 2: Determine if search is needed
            needs_search = await self._needs_search(query, context)
            result.search_triggered = needs_search
            
            # Step 3: Execute appropriate processing path
            if needs_multistep and MULTI_STEP_REASONING_ENABLED:
                # Complex query: use multi-step reasoning
                log.info("[ENHANCED-WEB] Using multi-step reasoning")
                result = await self._process_with_multistep(query, persona, result)
            elif needs_search:
                # Simple query with search
                log.info("[ENHANCED-WEB] Using search-enhanced response")
                result = await self._process_with_search(query, persona, result)
            else:
                # Direct LLM response
                log.info("[ENHANCED-WEB] Using direct LLM response")
                result = await self._process_direct(query, persona, result)
            
            # Step 4: Score source credibility
            if result.sources and CREDIBILITY_SCORING_ENABLED:
                result.sources = self._score_sources(result.sources)
                result.sources = self._filter_reliable_sources(result.sources)
            
            # Step 5: Add inline citations
            if enable_citations and result.sources and INLINE_CITATIONS_ENABLED:
                result = self._add_citations(result)
            
            # Step 6: Generate follow-up questions
            if enable_followups and FOLLOWUP_SUGGESTIONS_ENABLED:
                result.followup_questions = self._generate_followups(
                    query, result.text
                )
            
            log.info(f"[ENHANCED-WEB] Response ready: {len(result.text)} chars, "
                    f"{len(result.sources)} sources, confidence={result.confidence:.2f}")
            
        except Exception as e:
            log.error(f"[ENHANCED-WEB] Error: {e}", exc_info=True)
            result.text = f"Si è verificato un errore nell'elaborazione: {str(e)}"
            result.confidence = 0.0
        
        return result
    
    async def _analyze_complexity(self, query: str) -> Tuple[float, bool]:
        """Analyze query complexity."""
        if not MULTI_STEP_REASONING_ENABLED:
            return 0.0, False
        
        return await self.reasoner.analyze_complexity(query)
    
    async def _needs_search(
        self,
        query: str,
        context: Dict[str, Any]
    ) -> bool:
        """Determine if query needs web search."""
        try:
            from core.auto_search_detector import get_auto_search_detector
            detector = get_auto_search_detector()
            decision = await detector.should_trigger_search(query, context, {})
            return decision.get('should_search', False)
        except Exception as e:
            log.warning(f"Search detection error: {e}")
            # Default: search for non-conversational queries
            return not self._is_conversational(query)
    
    def _is_conversational(self, query: str) -> bool:
        """Check if query is conversational."""
        conversational_patterns = [
            r'^\s*(ciao|salve|hey|hi|hello)\s*$',
            r'^\s*(come\s+stai|come\s+va)\s*\??\s*$',
            r'^\s*(grazie|thanks|ok|perfetto)\s*$',
        ]
        query_lower = query.lower()
        return any(re.match(p, query_lower) for p in conversational_patterns)
    
    async def _process_with_multistep(
        self,
        query: str,
        persona: str,
        result: EnhancedWebResponse
    ) -> EnhancedWebResponse:
        """Process query with multi-step reasoning."""
        reasoning_result = await self.reasoner.reason(query, persona)
        
        result.text = reasoning_result.final_answer
        result.sources = reasoning_result.sources
        result.reasoning_trace = reasoning_result.reasoning_trace
        result.confidence = reasoning_result.confidence
        result.search_triggered = reasoning_result.total_steps > 1
        
        return result
    
    async def _process_with_search(
        self,
        query: str,
        persona: str,
        result: EnhancedWebResponse
    ) -> EnhancedWebResponse:
        """Process query with web search."""
        # Perform search
        if self.search_func:
            try:
                search_results = await self.search_func(query, 8)
                result.sources = search_results[:MAX_SOURCES_PER_RESPONSE]
            except Exception as e:
                log.warning(f"Search error: {e}")
                search_results = []
        else:
            search_results = []
        
        # Generate response with search context
        if search_results and self.llm_func:
            # Build context from search results
            snippets = "\n".join([
                f"[{i+1}] {r.get('title', '')}: {r.get('snippet', '')[:300]}"
                for i, r in enumerate(search_results[:5])
            ])
            
            synthesis_prompt = (
                f"REGOLA FONDAMENTALE: Rispondi SOLO usando le informazioni seguenti. "
                f"NON inventare dati non presenti nelle fonti.\n\n"
                f"FONTI DISPONIBILI:\n{snippets}\n\n"
                f"DOMANDA: {query}\n\n"
                f"Rispondi in modo accurato e completo:"
            )
            
            try:
                result.text = await self.llm_func(synthesis_prompt, persona)
                result.confidence = 0.8
            except Exception as e:
                log.error(f"LLM synthesis error: {e}")
                result.text = "Errore nella sintesi delle informazioni."
                result.confidence = 0.0
        else:
            # Fallback to direct LLM
            return await self._process_direct(query, persona, result)
        
        return result
    
    async def _process_direct(
        self,
        query: str,
        persona: str,
        result: EnhancedWebResponse
    ) -> EnhancedWebResponse:
        """Process query with direct LLM response."""
        if self.llm_func:
            try:
                result.text = await self.llm_func(query, persona)
                result.confidence = 0.7
            except Exception as e:
                log.error(f"LLM error: {e}")
                result.text = "Mi dispiace, si è verificato un errore."
                result.confidence = 0.0
        else:
            result.text = "LLM non disponibile."
            result.confidence = 0.0
        
        return result
    
    async def _basic_process(
        self,
        query: str,
        persona: str
    ) -> EnhancedWebResponse:
        """Basic processing without enhanced features."""
        result = EnhancedWebResponse(text="", confidence=0.0)
        
        if self.llm_func:
            try:
                result.text = await self.llm_func(query, persona)
                result.confidence = 0.6
            except Exception as e:
                result.text = f"Errore: {e}"
        
        return result
    
    def _score_sources(
        self,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Score sources for credibility."""
        return self.credibility_scorer.score_sources(sources)
    
    def _filter_reliable_sources(
        self,
        sources: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """Filter to keep only reliable sources."""
        return [
            s for s in sources
            if s.get('credibility', {}).get('overall_score', 0.5) >= MIN_CREDIBILITY_SCORE
        ][:MAX_SOURCES_PER_RESPONSE]
    
    def _add_citations(
        self,
        result: EnhancedWebResponse
    ) -> EnhancedWebResponse:
        """Add inline citations to response."""
        # Convert sources to format expected by citation formatter
        source_dicts = [
            {
                'url': s.get('url', ''),
                'title': s.get('title', ''),
                'snippet': s.get('snippet', ''),
            }
            for s in result.sources
        ]
        
        cited = self.citation_formatter.format_response(
            result.text,
            source_dicts,
            style="inline"
        )
        
        result.citations_text = cited.text
        result.text = cited.text
        
        return result
    
    def _generate_followups(
        self,
        query: str,
        response: str
    ) -> List[str]:
        """Generate follow-up question suggestions."""
        suggestions = self.followup_generator.generate_template_based(
            query, response, max_questions=3
        )
        return [s.question for s in suggestions]
    
    def format_for_telegram(
        self,
        result: EnhancedWebResponse,
        include_followups: bool = True
    ) -> str:
        """
        Format response for Telegram output.
        
        Args:
            result: Enhanced web response
            include_followups: Include follow-up suggestions
            
        Returns:
            Telegram-formatted string
        """
        parts = [result.text]
        
        # Add sources in compact format
        if result.sources:
            source_lines = ["\n\n📚 *Fonti:*"]
            for i, s in enumerate(result.sources[:3], 1):
                title = s.get('title', 'Fonte')
                if len(title) > 40:
                    title = title[:37] + "..."
                url = s.get('url', '')
                source_lines.append(f"[{i}] [{title}]({url})")
            parts.append('\n'.join(source_lines))
        
        # Add follow-ups
        if include_followups and result.followup_questions:
            followup_lines = ["\n\n💡 *Vuoi approfondire?*"]
            for q in result.followup_questions[:2]:
                followup_lines.append(f"• {q}")
            parts.append('\n'.join(followup_lines))
        
        # Add confidence indicator
        if result.confidence > 0:
            confidence_emoji = "🟢" if result.confidence >= 0.7 else "🟡" if result.confidence >= 0.4 else "🔴"
            parts.append(f"\n\n{confidence_emoji} Affidabilità: {result.confidence:.0%}")
        
        return '\n'.join(parts)
    
    def format_for_api(
        self,
        result: EnhancedWebResponse
    ) -> Dict[str, Any]:
        """
        Format response for API output.
        
        Args:
            result: Enhanced web response
            
        Returns:
            Dict with structured response data
        """
        return {
            "response": result.text,
            "sources": [
                {
                    "url": s.get("url", ""),
                    "title": s.get("title", ""),
                    "credibility": s.get("credibility", {}),
                }
                for s in result.sources
            ],
            "followup_questions": result.followup_questions,
            "reasoning_trace": result.reasoning_trace,
            "confidence": result.confidence,
            "search_triggered": result.search_triggered,
            "metadata": result.metadata,
        }


# === Singleton Instance ===
_engine_instance: Optional[EnhancedWebEngine] = None


def get_enhanced_web_engine(
    llm_func=None,
    search_func=None
) -> EnhancedWebEngine:
    """
    Get or create EnhancedWebEngine singleton.
    
    Args:
        llm_func: LLM function
        search_func: Search function
        
    Returns:
        EnhancedWebEngine instance
    """
    global _engine_instance
    
    if _engine_instance is None:
        _engine_instance = EnhancedWebEngine(
            llm_func=llm_func,
            search_func=search_func
        )
    else:
        if llm_func:
            _engine_instance.llm_func = llm_func
        if search_func:
            _engine_instance.search_func = search_func
    
    return _engine_instance


async def process_web_query(
    query: str,
    llm_func=None,
    search_func=None,
    persona: str = "",
    enable_citations: bool = True,
    enable_followups: bool = True
) -> Dict[str, Any]:
    """
    Utility function for enhanced web query processing.
    
    Args:
        query: User query
        llm_func: LLM function
        search_func: Search function
        persona: System persona
        enable_citations: Enable citations
        enable_followups: Enable follow-ups
        
    Returns:
        Dict with response and metadata
    """
    engine = get_enhanced_web_engine(llm_func, search_func)
    result = await engine.process_query(
        query,
        persona=persona,
        enable_citations=enable_citations,
        enable_followups=enable_followups
    )
    return engine.format_for_api(result)
