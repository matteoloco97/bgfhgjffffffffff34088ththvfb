#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/multi_step_reasoning.py — Multi-Step Reasoning for Complex Queries

Implements Claude-like query decomposition and multi-step reasoning:
- Automatically breaks complex queries into sub-questions
- Executes each step with appropriate tools/search
- Synthesizes final answer from all steps
- Provides reasoning trace for transparency

Author: QuantumDev Enhancement
Version: 1.0.0
"""

from __future__ import annotations

import os
import re
import logging
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

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


MULTI_STEP_ENABLED = _env_bool("MULTI_STEP_REASONING_ENABLED", True)
MAX_REASONING_STEPS = _env_int("MAX_REASONING_STEPS", 5)
STEP_TIMEOUT_S = _env_int("STEP_TIMEOUT_S", 30)


class StepType(str, Enum):
    """Types of reasoning steps."""
    SEARCH = "search"  # Web search for information
    CALCULATE = "calculate"  # Numerical calculation
    ANALYZE = "analyze"  # Deep analysis of data
    COMPARE = "compare"  # Compare multiple options
    SUMMARIZE = "summarize"  # Summarize findings
    VERIFY = "verify"  # Verify a claim or fact
    SYNTHESIZE = "synthesize"  # Combine multiple pieces


@dataclass
class ReasoningStep:
    """A single step in the reasoning chain."""
    step_num: int
    question: str
    step_type: StepType
    reasoning: str = ""
    result: str = ""
    sources: List[Dict[str, str]] = field(default_factory=list)
    confidence: float = 0.0
    completed: bool = False
    error: Optional[str] = None


@dataclass
class ReasoningPlan:
    """Complete plan for multi-step reasoning."""
    original_query: str
    steps: List[ReasoningStep] = field(default_factory=list)
    requires_decomposition: bool = False
    complexity_score: float = 0.0


@dataclass
class ReasoningResult:
    """Result of multi-step reasoning."""
    original_query: str
    final_answer: str
    steps: List[ReasoningStep] = field(default_factory=list)
    reasoning_trace: List[str] = field(default_factory=list)
    sources: List[Dict[str, str]] = field(default_factory=list)
    confidence: float = 0.0
    total_steps: int = 0
    completed_steps: int = 0


class MultiStepReasoner:
    """
    Multi-step reasoning engine for complex queries.
    
    Implements:
    - Query complexity detection
    - Automatic query decomposition
    - Step-by-step execution with appropriate tools
    - Result synthesis with reasoning trace
    """
    
    # Patterns that indicate complex queries
    COMPLEXITY_PATTERNS = [
        (r'\b(confronta|compara|compare|versus|vs)\b', 0.3),
        (r'\b(pro e contro|pros and cons|vantaggi e svantaggi)\b', 0.4),
        (r'\b(perché|perche|why|reason)\b.*\b(e|and)\b.*\b(come|how)\b', 0.4),
        (r'\b(analizza|analyze|analisi|analysis)\b', 0.3),
        (r'\b(migliore|best|peggiore|worst)\b.*\b(tra|between|among)\b', 0.3),
        (r'\b(qual è la differenza|what is the difference)\b', 0.3),
        (r'\b(step by step|passo passo|step-by-step)\b', 0.2),
        (r'\d+\s*(cose|things|motivi|reasons|modi|ways)\b', 0.3),
        (r'\b(primo|secondo|terzo|first|second|third)\b.*\b(poi|then|dopo|after)\b', 0.2),
    ]
    
    # Decomposition keywords
    DECOMPOSITION_KEYWORDS = [
        "e", "and", "inoltre", "also", "poi", "then", 
        "prima", "first", "dopo", "after", "infine", "finally",
        "sia", "both", "oppure", "or", "né", "nor",
    ]
    
    def __init__(self, llm_func=None, search_func=None):
        """
        Initialize multi-step reasoner.
        
        Args:
            llm_func: Async function to call LLM (user_text, persona) -> str
            search_func: Async function for web search (query, num) -> List[Dict]
        """
        self.llm_func = llm_func
        self.search_func = search_func
    
    async def analyze_complexity(self, query: str) -> Tuple[float, bool]:
        """
        Analyze query complexity to determine if multi-step reasoning is needed.
        
        Args:
            query: User query
            
        Returns:
            (complexity_score, requires_decomposition)
        """
        if not query:
            return 0.0, False
        
        query_lower = query.lower()
        complexity_score = 0.0
        
        # Check against complexity patterns
        for pattern, weight in self.COMPLEXITY_PATTERNS:
            if re.search(pattern, query_lower, re.IGNORECASE):
                complexity_score += weight
        
        # Check word count (longer queries tend to be more complex)
        word_count = len(query.split())
        if word_count > 20:
            complexity_score += 0.2
        elif word_count > 30:
            complexity_score += 0.3
        
        # Check for multiple question marks (multiple questions)
        question_count = query.count('?')
        if question_count > 1:
            complexity_score += 0.3 * min(question_count, 3)
        
        # Check for decomposition keywords
        for keyword in self.DECOMPOSITION_KEYWORDS:
            if f" {keyword} " in f" {query_lower} ":
                complexity_score += 0.1
        
        # Normalize to 0-1
        complexity_score = min(1.0, complexity_score)
        
        # Threshold for decomposition
        requires_decomposition = complexity_score >= 0.5
        
        log.debug(f"Query complexity: {complexity_score:.2f}, decompose: {requires_decomposition}")
        return complexity_score, requires_decomposition
    
    async def decompose_query(self, query: str) -> List[str]:
        """
        Decompose a complex query into simpler sub-questions.
        
        Args:
            query: Complex user query
            
        Returns:
            List of simpler sub-questions
        """
        if not self.llm_func:
            # Fallback: simple split on conjunctions
            return self._simple_decompose(query)
        
        decomposition_prompt = f"""Analizza questa domanda complessa e dividila in sotto-domande più semplici.

DOMANDA ORIGINALE: {query}

REGOLE:
1. Ogni sotto-domanda deve essere indipendente e rispondibile separatamente
2. Ordina le sotto-domande in ordine logico (le risposte precedenti potrebbero servire per le successive)
3. Massimo 4 sotto-domande
4. Se la domanda è già semplice, ripetila semplicemente

FORMATO OUTPUT:
Rispondi SOLO con le sotto-domande, una per riga, numerate così:
1. [prima sotto-domanda]
2. [seconda sotto-domanda]
..."""

        try:
            response = await self.llm_func(
                decomposition_prompt,
                "Sei un analizzatore di query. Decomponi query complesse in sotto-domande."
            )
            
            # Parse numbered questions
            sub_questions = []
            for line in response.strip().split('\n'):
                # Match numbered lines like "1. Question"
                match = re.match(r'^\d+[.)]\s*(.+)$', line.strip())
                if match:
                    question = match.group(1).strip()
                    if question and len(question) > 5:
                        sub_questions.append(question)
            
            if sub_questions:
                log.info(f"Decomposed into {len(sub_questions)} sub-questions")
                return sub_questions[:MAX_REASONING_STEPS]
            
        except Exception as e:
            log.warning(f"LLM decomposition failed: {e}")
        
        # Fallback
        return self._simple_decompose(query)
    
    def _simple_decompose(self, query: str) -> List[str]:
        """Simple rule-based decomposition."""
        # Split on common conjunctions
        parts = re.split(r'\s+(?:e|and|oppure|or|poi|then|inoltre|also)\s+', query, flags=re.IGNORECASE)
        
        # Clean and filter
        questions = []
        for part in parts:
            part = part.strip()
            if len(part) > 10:
                # Ensure it ends with question mark if it's a question
                if not part.endswith('?') and any(q in part.lower() for q in ['cosa', 'come', 'perché', 'quale', 'what', 'how', 'why', 'which']):
                    part += '?'
                questions.append(part)
        
        return questions if questions else [query]
    
    async def create_reasoning_plan(self, query: str) -> ReasoningPlan:
        """
        Create a reasoning plan for the query.
        
        Args:
            query: User query
            
        Returns:
            ReasoningPlan with steps
        """
        complexity_score, requires_decomposition = await self.analyze_complexity(query)
        
        plan = ReasoningPlan(
            original_query=query,
            requires_decomposition=requires_decomposition,
            complexity_score=complexity_score
        )
        
        if not requires_decomposition:
            # Single step for simple queries
            plan.steps = [
                ReasoningStep(
                    step_num=1,
                    question=query,
                    step_type=self._detect_step_type(query),
                )
            ]
        else:
            # Decompose and create steps
            sub_questions = await self.decompose_query(query)
            
            for i, sub_q in enumerate(sub_questions, 1):
                plan.steps.append(
                    ReasoningStep(
                        step_num=i,
                        question=sub_q,
                        step_type=self._detect_step_type(sub_q),
                    )
                )
            
            # Add synthesis step
            if len(plan.steps) > 1:
                plan.steps.append(
                    ReasoningStep(
                        step_num=len(plan.steps) + 1,
                        question=f"Sintetizza le risposte precedenti per rispondere a: {query}",
                        step_type=StepType.SYNTHESIZE,
                    )
                )
        
        return plan
    
    def _detect_step_type(self, question: str) -> StepType:
        """Detect the type of step needed for a question."""
        q_lower = question.lower()
        
        if any(kw in q_lower for kw in ['calcola', 'quanto fa', 'somma', 'calculate']):
            return StepType.CALCULATE
        elif any(kw in q_lower for kw in ['confronta', 'compare', 'differenza', 'difference']):
            return StepType.COMPARE
        elif any(kw in q_lower for kw in ['verifica', 'verify', 'vero', 'true', 'falso', 'false']):
            return StepType.VERIFY
        elif any(kw in q_lower for kw in ['riassumi', 'summarize', 'sintesi', 'summary']):
            return StepType.SUMMARIZE
        elif any(kw in q_lower for kw in ['analizza', 'analyze', 'analisi', 'analysis']):
            return StepType.ANALYZE
        else:
            return StepType.SEARCH
    
    async def execute_step(
        self,
        step: ReasoningStep,
        context: Dict[str, Any]
    ) -> ReasoningStep:
        """
        Execute a single reasoning step.
        
        Args:
            step: The step to execute
            context: Context from previous steps
            
        Returns:
            Updated step with results
        """
        try:
            if step.step_type == StepType.SEARCH:
                # Execute web search
                if self.search_func:
                    try:
                        results = await asyncio.wait_for(
                            self.search_func(step.question, 5),
                            timeout=STEP_TIMEOUT_S
                        )
                        step.sources = [
                            {"url": r.get("url", ""), "title": r.get("title", "")}
                            for r in results[:5]
                        ]
                        
                        # Synthesize search results
                        if results and self.llm_func:
                            snippets = "\n".join([
                                f"- {r.get('title', '')}: {r.get('snippet', '')[:200]}"
                                for r in results[:3]
                            ])
                            
                            synthesis_prompt = (
                                f"Basandoti su queste fonti:\n{snippets}\n\n"
                                f"Rispondi brevemente a: {step.question}"
                            )
                            step.result = await self.llm_func(synthesis_prompt, "")
                            step.confidence = 0.8
                        else:
                            step.result = "Nessun risultato trovato."
                            step.confidence = 0.3
                    except asyncio.TimeoutError:
                        step.error = "Timeout durante la ricerca"
                        step.confidence = 0.0
                else:
                    step.error = "Funzione di ricerca non disponibile"
                    step.confidence = 0.0
            
            elif step.step_type == StepType.SYNTHESIZE:
                # Synthesize previous results
                if self.llm_func:
                    prev_results = context.get("previous_results", [])
                    if prev_results:
                        context_str = "\n\n".join([
                            f"Passo {i+1}: {r}"
                            for i, r in enumerate(prev_results)
                        ])
                        
                        synthesis_prompt = (
                            f"Sintetizza queste informazioni per rispondere alla domanda originale.\n\n"
                            f"INFORMAZIONI RACCOLTE:\n{context_str}\n\n"
                            f"DOMANDA ORIGINALE: {context.get('original_query', step.question)}\n\n"
                            f"RISPOSTA SINTETIZZATA:"
                        )
                        step.result = await self.llm_func(synthesis_prompt, "")
                        step.confidence = 0.85
                    else:
                        step.result = "Nessun risultato da sintetizzare."
                        step.confidence = 0.0
                else:
                    step.error = "Funzione LLM non disponibile"
            
            elif step.step_type in [StepType.ANALYZE, StepType.COMPARE, StepType.VERIFY]:
                # Use LLM for analysis-type steps
                if self.llm_func:
                    step.result = await self.llm_func(step.question, "")
                    step.confidence = 0.7
                else:
                    step.error = "Funzione LLM non disponibile"
            
            else:
                # Default: use LLM
                if self.llm_func:
                    step.result = await self.llm_func(step.question, "")
                    step.confidence = 0.6
            
            step.completed = True
            step.reasoning = f"Eseguito {step.step_type.value} per: {step.question[:50]}..."
            
        except Exception as e:
            step.error = str(e)
            step.completed = False
            log.error(f"Step execution error: {e}")
        
        return step
    
    async def reason(self, query: str, persona: str = "") -> ReasoningResult:
        """
        Execute multi-step reasoning for a query.
        
        Args:
            query: User query
            persona: System persona for LLM
            
        Returns:
            ReasoningResult with complete reasoning chain
        """
        if not MULTI_STEP_ENABLED:
            # Fallback to simple processing
            return ReasoningResult(
                original_query=query,
                final_answer="Multi-step reasoning disabled.",
                confidence=0.0
            )
        
        # Create plan
        plan = await self.create_reasoning_plan(query)
        
        # Execute steps
        result = ReasoningResult(
            original_query=query,
            total_steps=len(plan.steps)
        )
        
        context = {
            "original_query": query,
            "previous_results": [],
            "all_sources": []
        }
        
        for step in plan.steps:
            # Add reasoning trace
            result.reasoning_trace.append(
                f"🔍 Passo {step.step_num}: {step.question}"
            )
            
            # Execute step
            executed_step = await self.execute_step(step, context)
            result.steps.append(executed_step)
            
            if executed_step.completed:
                result.completed_steps += 1
                context["previous_results"].append(executed_step.result)
                context["all_sources"].extend(executed_step.sources)
                
                result.reasoning_trace.append(
                    f"✅ Completato con confidenza {executed_step.confidence:.0%}"
                )
            else:
                result.reasoning_trace.append(
                    f"❌ Errore: {executed_step.error}"
                )
        
        # Set final answer from last step (usually synthesis)
        if result.steps:
            last_step = result.steps[-1]
            if last_step.completed:
                result.final_answer = last_step.result
                result.confidence = last_step.confidence
            else:
                # Fallback to concatenating all results
                all_results = [s.result for s in result.steps if s.result]
                result.final_answer = "\n\n".join(all_results)
                result.confidence = 0.5
        
        # Deduplicate sources
        seen_urls = set()
        for step in result.steps:
            for source in step.sources:
                url = source.get("url", "")
                if url and url not in seen_urls:
                    result.sources.append(source)
                    seen_urls.add(url)
        
        return result


# === Singleton Instance ===
_reasoner_instance: Optional[MultiStepReasoner] = None


def get_multi_step_reasoner(
    llm_func=None,
    search_func=None
) -> MultiStepReasoner:
    """
    Get or create MultiStepReasoner singleton.
    
    Args:
        llm_func: LLM function for reasoning
        search_func: Search function for web queries
        
    Returns:
        MultiStepReasoner instance
    """
    global _reasoner_instance
    
    if _reasoner_instance is None:
        _reasoner_instance = MultiStepReasoner(
            llm_func=llm_func,
            search_func=search_func
        )
    elif llm_func:
        _reasoner_instance.llm_func = llm_func
    elif search_func:
        _reasoner_instance.search_func = search_func
    
    return _reasoner_instance


async def reason_multi_step(
    query: str,
    llm_func=None,
    search_func=None,
    persona: str = ""
) -> Dict[str, Any]:
    """
    Utility function for multi-step reasoning.
    
    Args:
        query: User query
        llm_func: LLM function
        search_func: Search function
        persona: System persona
        
    Returns:
        Dict with reasoning results
    """
    reasoner = get_multi_step_reasoner(llm_func, search_func)
    result = await reasoner.reason(query, persona)
    
    return {
        "original_query": result.original_query,
        "final_answer": result.final_answer,
        "reasoning_trace": result.reasoning_trace,
        "sources": result.sources,
        "confidence": result.confidence,
        "total_steps": result.total_steps,
        "completed_steps": result.completed_steps,
        "steps": [
            {
                "step_num": s.step_num,
                "question": s.question,
                "type": s.step_type.value,
                "result": s.result[:500] if s.result else "",
                "confidence": s.confidence,
                "completed": s.completed,
            }
            for s in result.steps
        ]
    }
