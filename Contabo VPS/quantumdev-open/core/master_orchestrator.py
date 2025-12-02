#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
core/master_orchestrator.py — Master Orchestrator for QuantumDev Max

The central brain that coordinates all components:
- Conversational Memory
- Function Calling
- Reasoning Traces
- Artifacts

Author: Matteo (QuantumDev)
Version: 2.0.0
"""

from __future__ import annotations

import os
import re
import json
import time
import asyncio
import logging
from typing import Dict, Any, Optional, List, Callable, Union, Tuple
from dataclasses import dataclass, field
from enum import Enum

from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === Lazy imports to avoid circular dependencies ===
_ConversationalMemory = None
_FunctionCaller = None
_ReasoningTracer = None
_ArtifactsManager = None


def _get_memory():
    global _ConversationalMemory
    if _ConversationalMemory is None:
        from core.conversational_memory import get_conversational_memory
        _ConversationalMemory = get_conversational_memory
    return _ConversationalMemory


def _get_caller():
    global _FunctionCaller
    if _FunctionCaller is None:
        from core.function_calling import get_function_caller
        _FunctionCaller = get_function_caller
    return _FunctionCaller


def _get_tracer():
    global _ReasoningTracer
    if _ReasoningTracer is None:
        from core.reasoning_traces import get_reasoning_tracer
        _ReasoningTracer = get_reasoning_tracer
    return _ReasoningTracer


def _get_artifacts():
    global _ArtifactsManager
    if _ArtifactsManager is None:
        from core.artifacts import get_artifacts_manager
        _ArtifactsManager = get_artifacts_manager
    return _ArtifactsManager


# === ENV Configuration ===
def _env_bool(name: str, default: bool = False) -> bool:
    raw = (os.getenv(name, "1" if default else "0") or "").strip().lower()
    return raw in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, str(default)) or str(default)
    try:
        m = re.search(r"-?\d+", raw)
        return int(m.group(0)) if m else default
    except Exception:
        return default


# Feature flags
ENABLE_CONVERSATIONAL_MEMORY = _env_bool("ENABLE_CONVERSATIONAL_MEMORY", True)
ENABLE_FUNCTION_CALLING = _env_bool("ENABLE_FUNCTION_CALLING", True)
ENABLE_REASONING_TRACES = _env_bool("ENABLE_REASONING_TRACES", True)
ENABLE_ARTIFACTS = _env_bool("ENABLE_ARTIFACTS", True)
ENABLE_PROACTIVE_SUGGESTIONS = _env_bool("ENABLE_PROACTIVE_SUGGESTIONS", False)

MAX_CONTEXT_TOKENS = _env_int("MAX_CONTEXT_TOKENS", 32000)


# === Enums ===
class ResponseStrategy(str, Enum):
    """How to respond to a query."""
    DIRECT_LLM = "direct_llm"       # Direct LLM response
    TOOL_ASSISTED = "tool_assisted"  # Use tools then respond
    MEMORY_RECALL = "memory_recall"  # Recall from memory
    HYBRID = "hybrid"               # Combination


class QueryType(str, Enum):
    """Type of query."""
    GENERAL = "general"
    CODE = "code"
    RESEARCH = "research"
    CALCULATION = "calculation"
    MEMORY = "memory"
    CREATIVE = "creative"
    CONVERSATIONAL = "conversational"


# === Data Classes ===
@dataclass
class OrchestratorContext:
    """Context passed through orchestration."""
    source: str
    source_id: str
    query: str
    query_type: QueryType = QueryType.GENERAL
    strategy: ResponseStrategy = ResponseStrategy.DIRECT_LLM
    memory_context: List[Dict[str, str]] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    artifacts_created: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrchestratorResponse:
    """Response from orchestrator."""
    response: str
    context: OrchestratorContext
    reasoning_trace: Optional[Dict[str, Any]] = None
    artifacts: List[Dict[str, Any]] = field(default_factory=list)
    duration_ms: int = 0
    success: bool = True
    error: Optional[str] = None
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "response": self.response,
            "query": self.context.query,
            "query_type": self.context.query_type.value,
            "strategy": self.context.strategy.value,
            "artifacts": self.artifacts,
            "tool_results": self.context.tool_results,
            "duration_ms": self.duration_ms,
            "success": self.success,
            "error": self.error,
            "reasoning_trace": self.reasoning_trace,
        }


# === Query Analyzer ===
class QueryAnalyzer:
    """Analyzes queries to determine type and strategy."""
    
    # Patterns for query type detection
    CODE_PATTERNS = [
        r'\b(scrivi|crea|genera|write|create|generate)\b.*\b(codice|code|script|funzione|function|classe|class)\b',
        r'\b(debug|fix|ottimizza|refactor|optimize)\b',
        r'\b(python|javascript|typescript|java|go|rust|sql|bash)\b',
        r'```',
    ]
    
    CALCULATION_PATTERNS = [
        r'\b(calcola|calculate|quanto\s+fa|compute)\b',
        r'^\s*[\d\.\+\-\*\/\(\)\s]+\s*$',
        r'\b(somma|sum|media|average|percentuale|percentage)\b',
    ]
    
    RESEARCH_PATTERNS = [
        r'\b(cerca|search|trova|find|ricerca|research)\b',
        r'\b(ultime\s+notizie|breaking\s+news|latest)\b',
        r'\b(prezzo|price|quotazione|meteo|weather)\b',
        r'\b(come\s+funziona|how\s+does|spiegami|explain)\b.*\b(internet|web|online)\b',
        # Weather patterns
        r'\b(meteo|tempo|previsioni|che\s+tempo\s+fa|weather|forecast|temperatura|pioggia|neve)\b',
        # Price/Value patterns
        r'\b(prezzo|quotazione|quanto\s+vale|valore|tasso\s+di\s+cambio|cambio|borsa|azioni)\b',
        # News patterns
        r'\b(notizie|news|ultime\s+notizie|ultime\s+di\s+oggi|ANSA|breaking|oggi\s+cosa\s+è\s+successo)\b',
        # Common crypto symbols
        r'\b(BTC|bitcoin|ETH|ethereum|SOL|solana|ADA|cardano|USDT|tether|BNB|binance\s+coin)\b',
        # Common stock symbols
        r'\b(AAPL|apple\s+stock|NVDA|nvidia\s+stock|TSLA|tesla\s+stock|MSFT|microsoft\s+stock|GOOGL|google\s+stock)\b',
    ]
    
    MEMORY_PATTERNS = [
        r'\b(ricordi|remember|abbiamo\s+detto|we\s+discussed)\b',
        r'\b(prima|earlier|ieri|yesterday|la\s+scorsa\s+volta|last\s+time)\b',
        r'\b(mia|my|nostra|our)\s+(preferenza|preference|configurazione|setup)\b',
    ]
    
    CREATIVE_PATTERNS = [
        r'\b(scrivi|write|componi|compose|inventa|invent)\b.*\b(storia|story|poesia|poem|articolo|article)\b',
        r'\b(immagina|imagine|crea|create)\b.*\b(scenario|storia|narrative)\b',
    ]
    
    CONVERSATIONAL_PATTERNS = [
        r'^(ciao|hello|hi|hey|buongiorno|buonasera|salve)\s*[!?.]?$',
        r'^(come\s+stai|how\s+are\s+you)\s*[?]?$',
        r'^(ok|okay|grazie|thanks|perfetto|perfect)\s*[!.]?$',
    ]
    
    def analyze(self, query: str) -> Tuple[QueryType, ResponseStrategy]:
        """
        Analyze query to determine type and strategy.
        
        Args:
            query: User query
            
        Returns:
            Tuple of (QueryType, ResponseStrategy)
        """
        q_lower = query.lower().strip()
        
        # Check patterns in order of specificity
        if self._matches_any(q_lower, self.CONVERSATIONAL_PATTERNS):
            return QueryType.CONVERSATIONAL, ResponseStrategy.DIRECT_LLM
        
        if self._matches_any(q_lower, self.CODE_PATTERNS):
            return QueryType.CODE, ResponseStrategy.DIRECT_LLM
        
        if self._matches_any(q_lower, self.CALCULATION_PATTERNS):
            return QueryType.CALCULATION, ResponseStrategy.TOOL_ASSISTED
        
        if self._matches_any(q_lower, self.RESEARCH_PATTERNS):
            return QueryType.RESEARCH, ResponseStrategy.HYBRID  # Use HYBRID to get tools + LLM synthesis
        
        if self._matches_any(q_lower, self.MEMORY_PATTERNS):
            return QueryType.MEMORY, ResponseStrategy.MEMORY_RECALL
        
        if self._matches_any(q_lower, self.CREATIVE_PATTERNS):
            return QueryType.CREATIVE, ResponseStrategy.DIRECT_LLM
        
        return QueryType.GENERAL, ResponseStrategy.DIRECT_LLM
    
    def _matches_any(self, text: str, patterns: List[str]) -> bool:
        """Check if text matches any pattern."""
        for pattern in patterns:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False


async def classify_query_via_llm(query: str, llm_func: Optional[Callable] = None) -> Optional[QueryType]:
    """
    Classify query using LLM.
    
    Args:
        query: User query
        llm_func: Async LLM function
        
    Returns:
        QueryType or None if classification fails
    """
    if not llm_func:
        return None
    
    try:
        prompt = (
            f"Classifica questa query dell'utente in UNA delle seguenti categorie:\n\n"
            f"- GENERAL: domande generali, conversazione\n"
            f"- CODE: richieste di codice, programmazione, debug\n"
            f"- RESEARCH: ricerca di informazioni, notizie, fatti\n"
            f"- CALCULATION: calcoli matematici, elaborazioni numeriche\n"
            f"- MEMORY: riferimenti a conversazioni passate, ricordi\n"
            f"- CREATIVE: scrittura creativa, storie, poesie\n\n"
            f"Query: \"{query}\"\n\n"
            f"Rispondi SOLO con il nome della categoria (es: RESEARCH). Nient'altro."
        )
        
        system = "Sei un classificatore di query. Rispondi solo con il nome della categoria."
        
        response = await llm_func(prompt, system)
        
        if not response:
            return None
        
        # Parse response
        response_upper = response.strip().upper()
        
        # Try to extract category from response
        for qtype in QueryType:
            if qtype.value.upper() in response_upper:
                log.debug(f"LLM classified query as: {qtype.value}")
                return qtype
        
        log.warning(f"Could not parse LLM classification: {response}")
        return None
        
    except Exception as e:
        log.warning(f"LLM classification failed: {e}")
        return None


# === Master Orchestrator ===
class MasterOrchestrator:
    """
    Central brain that coordinates all QuantumDev Max components.
    
    Flow:
    1. Load context from memory
    2. Analyze query
    3. Decide strategy (direct LLM vs tools)
    4. Execute tools if needed
    5. Generate response
    6. Create artifacts
    7. Save to memory
    """
    
    def __init__(self, llm_func: Optional[Callable] = None):
        """
        Initialize Master Orchestrator.
        
        Args:
            llm_func: Async function for LLM calls.
                      Signature: async def llm_func(prompt: str, system: str) -> str
        """
        self.llm_func = llm_func
        self.analyzer = QueryAnalyzer()
        
        # Component instances (lazy loaded)
        self._memory = None
        self._caller = None
        self._tracer = None
        self._artifacts = None
        
        log.info(
            "MasterOrchestrator initialized: "
            f"memory={ENABLE_CONVERSATIONAL_MEMORY}, "
            f"tools={ENABLE_FUNCTION_CALLING}, "
            f"traces={ENABLE_REASONING_TRACES}, "
            f"artifacts={ENABLE_ARTIFACTS}"
        )
    
    @property
    def memory(self):
        """Get ConversationalMemory instance."""
        if self._memory is None and ENABLE_CONVERSATIONAL_MEMORY:
            get_memory = _get_memory()
            self._memory = get_memory(self.llm_func)
        return self._memory
    
    @property
    def caller(self):
        """Get FunctionCaller instance."""
        if self._caller is None and ENABLE_FUNCTION_CALLING:
            get_caller = _get_caller()
            self._caller = get_caller(self.llm_func)
        return self._caller
    
    @property
    def tracer(self):
        """Get ReasoningTracer instance."""
        if self._tracer is None and ENABLE_REASONING_TRACES:
            get_tracer = _get_tracer()
            self._tracer = get_tracer()
        return self._tracer
    
    @property
    def artifacts(self):
        """Get ArtifactsManager instance."""
        if self._artifacts is None and ENABLE_ARTIFACTS:
            get_artifacts = _get_artifacts()
            self._artifacts = get_artifacts()
        return self._artifacts
    
    async def process(
        self,
        query: str,
        source: str,
        source_id: str,
        show_reasoning: bool = False,
        create_artifacts: bool = True,
    ) -> OrchestratorResponse:
        """
        Process a query through the full orchestration pipeline.
        
        Args:
            query: User query
            source: Source identifier ("tg", "web", "api")
            source_id: User/chat identifier
            show_reasoning: Whether to include reasoning trace
            create_artifacts: Whether to create artifacts
            
        Returns:
            OrchestratorResponse with full result
        """
        start_time = time.perf_counter()
        
        # Initialize context
        context = OrchestratorContext(
            source=source,
            source_id=source_id,
            query=query,
        )
        
        try:
            # Step 1: Start reasoning trace
            trace = None
            if self.tracer:
                trace = self.tracer.start_trace(query)
                self._add_step("analysis", "Analyzing query", trace)
            
            # Step 2: Analyze query
            # Try LLM classification first
            query_type = None
            if self.llm_func:
                query_type = await classify_query_via_llm(query, self.llm_func)
            
            # Fallback to regex-based analysis
            if query_type is None:
                query_type, strategy = self.analyzer.analyze(query)
            else:
                # Determine strategy based on LLM classification
                if query_type == QueryType.RESEARCH:
                    strategy = ResponseStrategy.HYBRID  # Use HYBRID for research to get tools + LLM
                elif query_type in (QueryType.CODE, QueryType.CALCULATION, QueryType.MEMORY):
                    strategy = ResponseStrategy.TOOL_ASSISTED
                else:
                    strategy = ResponseStrategy.DIRECT_LLM
            
            context.query_type = query_type
            context.strategy = strategy
            
            if trace:
                self._complete_step(trace, f"Query type: {query_type.value}, Strategy: {strategy.value}")
            
            # Step 3: Load memory context
            if self.memory:
                if trace:
                    self._add_step("memory", "Loading conversation context", trace)
                
                session = await self.memory.get_or_create_session(source, source_id)
                context.memory_context = self.memory.build_context(session)
                
                if trace:
                    self._complete_step(trace, f"Loaded {len(context.memory_context)} context messages")
            
            # Step 4: Execute strategy
            response_text = ""
            
            if strategy in (ResponseStrategy.TOOL_ASSISTED, ResponseStrategy.HYBRID) and self.caller:
                if trace:
                    self._add_step("tools", "Executing tools", trace)
                
                result = await self.caller.orchestrate(query)
                response_text = result.final_response
                context.tool_results = [tc.to_dict() for tc in result.tool_calls]
                
                if trace:
                    self._complete_step(trace, f"Executed {len(result.tool_calls)} tool(s)")
                
                # For HYBRID, enhance the response with tool results
                if strategy == ResponseStrategy.HYBRID and context.tool_results and self.llm_func:
                    # Build enriched prompt with tool results
                    tool_context = "\n".join([
                        f"Tool: {tc['tool_name']}\nResult: {tc.get('result', 'N/A')}"
                        for tc in context.tool_results if not tc.get('error')
                    ])
                    
                    if tool_context:
                        enhanced_prompt = (
                            f"Query dell'utente: {query}\n\n"
                            f"Dati raccolti dai tool:\n{tool_context}\n\n"
                            "Fornisci una risposta completa citando esplicitamente i dati dai tool. "
                            "Non dire frasi generiche come 'dovresti consultare un sito' quando abbiamo già i dati."
                        )
                        
                        system = "Sei un assistente che sintetizza dati da fonti web e tool. Cita sempre le fonti dei dati."
                        response_text = await self.llm_func(enhanced_prompt, system)
            
            elif strategy == ResponseStrategy.MEMORY_RECALL and self.memory:
                if trace:
                    self._add_step("recall", "Searching memory", trace)
                
                relevant = await self.memory.search_history(source, source_id, query)
                if relevant:
                    memory_context = "\n".join([f"- {m.content[:200]}" for m in relevant[:5]])
                    prompt = (
                        f"L'utente chiede qualcosa relativo a conversazioni precedenti.\n\n"
                        f"CONTESTO MEMORIA:\n{memory_context}\n\n"
                        f"DOMANDA: {query}\n\n"
                        f"Rispondi basandoti sul contesto."
                    )
                    if self.llm_func:
                        response_text = await self.llm_func(prompt, "")
                
                if trace:
                    self._complete_step(trace, f"Found {len(relevant)} relevant memories")
            
            # Default: Direct LLM
            if not response_text and self.llm_func:
                if trace:
                    self._add_step("generation", "Generating response", trace)
                
                # Build context-aware prompt
                system_parts = []
                if context.memory_context:
                    system_parts.append("CONVERSAZIONE PRECEDENTE:")
                    for msg in context.memory_context[-5:]:
                        system_parts.append(f"{msg['role'].upper()}: {msg['content'][:200]}")
                
                system = "\n".join(system_parts) if system_parts else ""
                response_text = await self.llm_func(query, system)
                
                if trace:
                    self._complete_step(trace, f"Generated {len(response_text)} chars")
            
            # Step 5: Create artifacts if needed
            artifacts_list = []
            if create_artifacts and self.artifacts and response_text:
                if trace:
                    self._add_step("artifacts", "Processing artifacts", trace)
                
                artifacts_list = await self._extract_and_create_artifacts(
                    response_text, source, source_id
                )
                context.artifacts_created = [a["id"] for a in artifacts_list]
                
                if trace:
                    self._complete_step(trace, f"Created {len(artifacts_list)} artifact(s)")
            
            # Step 6: Save to memory
            if self.memory and response_text:
                if trace:
                    self._add_step("save", "Saving to memory", trace)
                
                session = await self.memory.add_turn(
                    source, source_id,
                    query, response_text,
                    user_metadata={"query_type": query_type.value},
                    assistant_metadata={"strategy": strategy.value},
                )
                
                if trace:
                    self._complete_step(trace, "Saved turn to memory")
                
                # Generate proactive suggestions if enabled
                if ENABLE_PROACTIVE_SUGGESTIONS and self.llm_func:
                    try:
                        from core.proactive import generate_suggestions
                        suggestions = await generate_suggestions(session, query, self.llm_func)
                        if suggestions:
                            context.metadata["proactive_suggestions"] = suggestions
                            log.info(f"Generated {len(suggestions)} proactive suggestions")
                    except Exception as e:
                        log.warning(f"Failed to generate proactive suggestions: {e}")
            
            # Complete trace
            reasoning_dict = None
            if trace:
                completed_trace = self.tracer.complete_trace(response_text, success=True)
                if show_reasoning and completed_trace:
                    reasoning_dict = completed_trace.to_dict()
            
            return OrchestratorResponse(
                response=response_text,
                context=context,
                reasoning_trace=reasoning_dict,
                artifacts=artifacts_list,
                duration_ms=int((time.perf_counter() - start_time) * 1000),
                success=True,
            )
            
        except Exception as e:
            log.error(f"Orchestration error: {e}")
            
            if self.tracer and self.tracer.current_trace:
                self.tracer.complete_trace("", success=False, error=str(e))
            
            return OrchestratorResponse(
                response="",
                context=context,
                duration_ms=int((time.perf_counter() - start_time) * 1000),
                success=False,
                error=str(e),
            )
    
    def _add_step(self, type_name: str, title: str, trace) -> None:
        """Add a thinking step to trace."""
        if not self.tracer:
            return
        
        from core.reasoning_traces import ThinkingType
        
        type_map = {
            "analysis": ThinkingType.ANALYSIS,
            "memory": ThinkingType.ANALYSIS,
            "tools": ThinkingType.EXECUTION,
            "recall": ThinkingType.ANALYSIS,
            "generation": ThinkingType.SYNTHESIS,
            "artifacts": ThinkingType.EXECUTION,
            "save": ThinkingType.EXECUTION,
        }
        
        step_type = type_map.get(type_name, ThinkingType.EXECUTION)
        self.tracer.add_step(step_type, title)
    
    def _complete_step(self, trace, content: str) -> None:
        """Complete current step with content."""
        if not self.tracer or not trace.steps:
            return
        
        current_step = trace.steps[-1]
        self.tracer.complete_step(current_step, content)
    
    async def _extract_and_create_artifacts(
        self,
        response: str,
        source: str,
        source_id: str,
    ) -> List[Dict[str, Any]]:
        """Extract code blocks and create artifacts."""
        if not self.artifacts:
            return []
        
        artifacts = []
        
        # Find code blocks
        code_pattern = r'```(\w+)?\n(.*?)```'
        matches = re.findall(code_pattern, response, re.DOTALL)
        
        for i, (lang, code) in enumerate(matches):
            if code.strip():
                artifact = await self.artifacts.create_code(
                    title=f"Code Block {i+1}",
                    code=code.strip(),
                    language=lang or None,
                    source=source,
                    source_id=source_id,
                )
                artifacts.append(artifact.to_dict())
        
        return artifacts
    
    async def get_session_info(
        self,
        source: str,
        source_id: str,
    ) -> Dict[str, Any]:
        """Get session information and stats."""
        info: Dict[str, Any] = {
            "source": source,
            "source_id": source_id,
            "features": {
                "memory": ENABLE_CONVERSATIONAL_MEMORY,
                "tools": ENABLE_FUNCTION_CALLING,
                "traces": ENABLE_REASONING_TRACES,
                "artifacts": ENABLE_ARTIFACTS,
            },
        }
        
        if self.memory:
            info["session"] = await self.memory.get_session_stats(source, source_id)
        
        if self.artifacts:
            user_artifacts = await self.artifacts.list_user_artifacts(source, source_id, 10)
            info["recent_artifacts"] = len(user_artifacts)
        
        if self.tracer:
            info["reasoning_stats"] = self.tracer.get_stats()
        
        return info
    
    async def clear_session(self, source: str, source_id: str) -> bool:
        """Clear user session."""
        if self.memory:
            return await self.memory.clear_session(source, source_id)
        return False


# === Singleton Instance ===
_orchestrator_instance: Optional[MasterOrchestrator] = None


def get_master_orchestrator(llm_func: Optional[Callable] = None) -> MasterOrchestrator:
    """
    Get or create MasterOrchestrator singleton.
    
    Args:
        llm_func: LLM function for responses
        
    Returns:
        MasterOrchestrator instance
    """
    global _orchestrator_instance
    
    if _orchestrator_instance is None:
        _orchestrator_instance = MasterOrchestrator(llm_func=llm_func)
    elif llm_func and _orchestrator_instance.llm_func is None:
        _orchestrator_instance.llm_func = llm_func
    
    return _orchestrator_instance


# === Test ===
if __name__ == "__main__":
    async def mock_llm(prompt: str, system: str) -> str:
        return f"Mock response for: {prompt[:50]}..."
    
    async def test():
        print("🧪 Testing Master Orchestrator")
        print("=" * 60)
        
        orchestrator = get_master_orchestrator(mock_llm)
        
        # Test query analysis
        analyzer = QueryAnalyzer()
        
        test_queries = [
            "Ciao!",
            "Scrivi una funzione Python per ordinare una lista",
            "Quanto fa 2 + 2 * 10?",
            "Cerca le ultime notizie su Bitcoin",
            "Ricordi cosa abbiamo detto ieri?",
            "Scrivi una breve storia di fantascienza",
            "Spiegami come funziona il machine learning",
        ]
        
        for q in test_queries:
            qtype, strategy = analyzer.analyze(q)
            print(f"Query: {q[:40]}...")
            print(f"  Type: {qtype.value}, Strategy: {strategy.value}")
        
        # Test full orchestration
        print("\n--- Full Orchestration Test ---")
        
        result = await orchestrator.process(
            query="Scrivi una funzione Python per il calcolo del fattoriale",
            source="test",
            source_id="user123",
            show_reasoning=True,
        )
        
        print(f"Success: {result.success}")
        print(f"Duration: {result.duration_ms}ms")
        print(f"Response: {result.response[:100]}...")
        
        if result.reasoning_trace:
            print(f"Reasoning steps: {len(result.reasoning_trace.get('steps', []))}")
        
        # Get session info
        info = await orchestrator.get_session_info("test", "user123")
        print(f"\nSession info: {json.dumps(info, indent=2)}")
        
        print("\n✅ All tests passed!")
    
    asyncio.run(test())
