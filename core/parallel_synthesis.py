#!/usr/bin/env python3
"""
parallel_synthesis.py
=====================
Parallel synthesis engine for web search results.

Processes multiple documents concurrently using asyncio to reduce total synthesis time
from 10-15s (sequential) to 3-5s (parallel).

Features:
- Process up to 3 documents concurrently
- Each synthesis limited to 80 tokens (configurable)
- Retry logic for failed syntheses (max 2 retries)
- Graceful degradation on timeout
- Merge results into coherent response
- Comprehensive logging with [PARALLEL] prefix
- Performance metrics tracking

Example Usage:
    ```python
    from core.parallel_synthesis import parallel_synthesize_documents
    
    documents = [
        {"idx": 1, "title": "Article 1", "url": "https://...", "text": "..."},
        {"idx": 2, "title": "Article 2", "url": "https://...", "text": "..."},
        {"idx": 3, "title": "Article 3", "url": "https://...", "text": "..."},
    ]
    
    synthesis = await parallel_synthesize_documents(
        query="quantum computing advances 2024",
        documents=documents,
        max_concurrent=3,
        timeout=5.0,
        token_limit=80,
        retry_attempts=2,
    )
    ```
"""

from __future__ import annotations

import os
import time
import asyncio
import logging
from typing import List, Dict, Any, Optional, Tuple
from dotenv import load_dotenv

load_dotenv()

log = logging.getLogger(__name__)

# === Configuration (from environment) ===
def _env_int(name: str, default: int) -> int:
    """Parse integer from environment variable."""
    raw = os.getenv(name, str(default)) or str(default)
    try:
        return int(raw)
    except Exception:
        return default

def _env_float(name: str, default: float) -> float:
    """Parse float from environment variable."""
    raw = os.getenv(name, str(default)) or str(default)
    try:
        return float(raw)
    except Exception:
        return default

def _env_bool(name: str, default: bool) -> bool:
    """Parse boolean from environment variable."""
    raw = os.getenv(name, "").lower()
    if raw in ("1", "true", "yes", "on"):
        return True
    if raw in ("0", "false", "no", "off"):
        return False
    return default

# Parallel synthesis configuration
PARALLEL_SYNTHESIS_ENABLED = _env_bool("PARALLEL_SYNTHESIS_ENABLED", True)
PARALLEL_SYNTHESIS_MAX_CONCURRENT = _env_int("PARALLEL_SYNTHESIS_MAX_CONCURRENT", 3)
PARALLEL_SYNTHESIS_TIMEOUT = _env_float("PARALLEL_SYNTHESIS_TIMEOUT", 5.0)
PARALLEL_SYNTHESIS_TOKEN_LIMIT = _env_int("PARALLEL_SYNTHESIS_TOKEN_LIMIT", 80)
PARALLEL_SYNTHESIS_RETRY_ATTEMPTS = _env_int("PARALLEL_SYNTHESIS_RETRY_ATTEMPTS", 2)


async def _synthesize_single_document(
    query: str,
    document: Dict[str, Any],
    persona: str,
    token_limit: int,
    timeout: float,
    retry_attempts: int,
) -> Tuple[Optional[str], Dict[str, Any]]:
    """
    Synthesize a single document with retry logic.
    
    Args:
        query: User query
        document: Document dict with {idx, title, url, text}
        persona: System persona/prompt
        token_limit: Maximum tokens for synthesis
        timeout: Timeout in seconds
        retry_attempts: Maximum number of retry attempts
        
    Returns:
        Tuple of (synthesis text or None, stats dict)
    """
    from core.chat_engine import reply_with_llm
    from backend.synthesis_prompt_v2 import build_aggressive_synthesis_prompt
    
    doc_idx = document.get("idx", 0)
    doc_title = document.get("title", "Untitled")[:60]
    stats = {
        "idx": doc_idx,
        "title": doc_title,
        "attempts": 0,
        "success": False,
        "error": None,
        "duration_ms": 0,
    }
    
    start_time = time.perf_counter()
    
    for attempt in range(1, retry_attempts + 2):  # 1 initial + retry_attempts retries
        stats["attempts"] = attempt
        
        try:
            # Build synthesis prompt for single document
            prompt = build_aggressive_synthesis_prompt(query, [document])
            
            # Call LLM with timeout and token limit
            synthesis = await asyncio.wait_for(
                reply_with_llm(
                    prompt,
                    persona,
                    temperature=0.3,  # Lower temperature for more focused synthesis
                    max_tokens=token_limit,
                ),
                timeout=timeout
            )
            
            if synthesis and len(synthesis.strip()) > 10:  # Valid synthesis
                stats["success"] = True
                stats["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
                log.info(f"[PARALLEL] Doc {doc_idx} synthesized successfully (attempt {attempt}, {stats['duration_ms']}ms)")
                return synthesis.strip(), stats
            else:
                log.warning(f"[PARALLEL] Doc {doc_idx} returned empty synthesis (attempt {attempt})")
                
        except asyncio.TimeoutError:
            log.warning(f"[PARALLEL] Doc {doc_idx} timeout on attempt {attempt}/{retry_attempts + 1}")
            stats["error"] = "timeout"
            
        except Exception as e:
            log.warning(f"[PARALLEL] Doc {doc_idx} failed on attempt {attempt}/{retry_attempts + 1}: {e}")
            stats["error"] = str(e)
        
        # Exponential backoff between retries
        if attempt <= retry_attempts:
            await asyncio.sleep(0.5 * attempt)
    
    # All attempts failed
    stats["duration_ms"] = int((time.perf_counter() - start_time) * 1000)
    log.error(f"[PARALLEL] Doc {doc_idx} failed after {stats['attempts']} attempts")
    return None, stats


async def parallel_synthesize_documents(
    query: str,
    documents: List[Dict[str, Any]],
    persona: str = "",
    max_concurrent: Optional[int] = None,
    timeout: Optional[float] = None,
    token_limit: Optional[int] = None,
    retry_attempts: Optional[int] = None,
) -> Tuple[str, Dict[str, Any]]:
    """
    Synthesize multiple documents in parallel using asyncio.
    
    This function processes multiple web search documents concurrently to reduce
    total synthesis time from 10-15s (sequential) to 3-5s (parallel).
    
    Args:
        query: User query string
        documents: List of document dicts with {idx, title, url, text}
        persona: System persona/prompt (default: empty string)
        max_concurrent: Maximum concurrent syntheses (default: from env or 3)
        timeout: Timeout per document in seconds (default: from env or 5.0)
        token_limit: Maximum tokens per synthesis (default: from env or 80)
        retry_attempts: Maximum retry attempts (default: from env or 2)
        
    Returns:
        Tuple of (merged synthesis text, stats dict)
        
    Example:
        >>> docs = [
        ...     {"idx": 1, "title": "Doc 1", "url": "https://...", "text": "..."},
        ...     {"idx": 2, "title": "Doc 2", "url": "https://...", "text": "..."},
        ... ]
        >>> synthesis, stats = await parallel_synthesize_documents(
        ...     "quantum computing",
        ...     docs,
        ... )
        >>> print(f"Synthesis: {synthesis}")
        >>> print(f"Success rate: {stats['success_rate']}")
    """
    start_time = time.perf_counter()
    
    # Apply defaults from environment
    max_concurrent = max_concurrent or PARALLEL_SYNTHESIS_MAX_CONCURRENT
    timeout = timeout or PARALLEL_SYNTHESIS_TIMEOUT
    token_limit = token_limit or PARALLEL_SYNTHESIS_TOKEN_LIMIT
    retry_attempts = retry_attempts or PARALLEL_SYNTHESIS_RETRY_ATTEMPTS
    
    # Validate inputs
    if not documents:
        log.warning("[PARALLEL] No documents to synthesize")
        return "", {
            "total_documents": 0,
            "successful": 0,
            "failed": 0,
            "success_rate": 0.0,
            "total_duration_ms": 0,
            "speedup": 1.0,
        }
    
    # Limit concurrent tasks
    docs_to_process = documents[:max_concurrent]
    log.info(f"[PARALLEL] Starting synthesis of {len(docs_to_process)}/{len(documents)} documents (max_concurrent={max_concurrent})")
    
    # Create tasks for parallel execution
    tasks = [
        _synthesize_single_document(
            query=query,
            document=doc,
            persona=persona,
            token_limit=token_limit,
            timeout=timeout,
            retry_attempts=retry_attempts,
        )
        for doc in docs_to_process
    ]
    
    # Execute all tasks concurrently
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Collect successful syntheses and stats
    syntheses = []
    all_stats = []
    successful = 0
    failed = 0
    
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            log.error(f"[PARALLEL] Task {i+1} raised exception: {result}")
            failed += 1
            all_stats.append({
                "idx": i + 1,
                "success": False,
                "error": str(result),
                "attempts": 0,
                "duration_ms": 0,
            })
        else:
            synthesis, doc_stats = result
            all_stats.append(doc_stats)
            
            if synthesis:
                syntheses.append(synthesis)
                successful += 1
            else:
                failed += 1
    
    total_duration_ms = int((time.perf_counter() - start_time) * 1000)
    
    # Merge syntheses into coherent response
    merged_synthesis = _merge_syntheses(syntheses) if syntheses else ""
    
    # Calculate stats
    success_rate = successful / len(docs_to_process) if docs_to_process else 0.0
    
    # Estimate speedup (assuming sequential would take timeout * num_docs)
    estimated_sequential_ms = int(timeout * 1000 * len(docs_to_process))
    speedup = estimated_sequential_ms / total_duration_ms if total_duration_ms > 0 else 1.0
    
    stats = {
        "total_documents": len(docs_to_process),
        "successful": successful,
        "failed": failed,
        "success_rate": success_rate,
        "total_duration_ms": total_duration_ms,
        "estimated_sequential_ms": estimated_sequential_ms,
        "speedup": round(speedup, 1),
        "document_stats": all_stats,
    }
    
    # Log summary
    log.info(
        f"[PARALLEL] Synthesis complete: {successful}/{len(docs_to_process)} successful "
        f"in {total_duration_ms}ms (estimated sequential: {estimated_sequential_ms}ms, "
        f"{speedup:.1f}x speedup)"
    )
    
    if failed > 0:
        log.warning(f"[PARALLEL] {failed} documents failed synthesis")
    
    return merged_synthesis, stats


def _merge_syntheses(syntheses: List[str]) -> str:
    """
    Merge multiple syntheses into a coherent response.
    
    Strategy:
    - Combine all syntheses with proper formatting
    - Preserve structure from individual syntheses
    - Add separators for readability
    
    Args:
        syntheses: List of synthesis strings
        
    Returns:
        Merged synthesis string
    """
    if not syntheses:
        return ""
    
    if len(syntheses) == 1:
        return syntheses[0]
    
    # Merge syntheses with minimal formatting
    # Most syntheses already have TL;DR + bullet points format
    # Just concatenate and let the structure speak for itself
    merged = "\n\n".join(syntheses)
    
    return merged


def is_parallel_synthesis_enabled() -> bool:
    """
    Check if parallel synthesis is enabled.
    
    Returns:
        True if parallel synthesis is enabled, False otherwise
    """
    return PARALLEL_SYNTHESIS_ENABLED


def get_parallel_synthesis_config() -> Dict[str, Any]:
    """
    Get current parallel synthesis configuration.
    
    Returns:
        Dict with configuration parameters
    """
    return {
        "enabled": PARALLEL_SYNTHESIS_ENABLED,
        "max_concurrent": PARALLEL_SYNTHESIS_MAX_CONCURRENT,
        "timeout": PARALLEL_SYNTHESIS_TIMEOUT,
        "token_limit": PARALLEL_SYNTHESIS_TOKEN_LIMIT,
        "retry_attempts": PARALLEL_SYNTHESIS_RETRY_ATTEMPTS,
    }


# === Example usage and testing ===
async def _test_parallel_synthesis():
    """Test parallel synthesis with mock documents."""
    print("="*80)
    print("Testing Parallel Synthesis Engine")
    print("="*80)
    
    # Mock documents
    documents = [
        {
            "idx": 1,
            "title": "Quantum Computing Breakthrough 2024",
            "url": "https://example.com/1",
            "text": "Scientists achieved quantum supremacy with new 1000-qubit processor. Error rates reduced by 50%.",
        },
        {
            "idx": 2,
            "title": "Google's Quantum Chip Advances",
            "url": "https://example.com/2",
            "text": "Google announced Willow chip with improved coherence times. Can solve problems in 5 minutes that would take supercomputers 10 billion years.",
        },
        {
            "idx": 3,
            "title": "IBM Quantum Roadmap",
            "url": "https://example.com/3",
            "text": "IBM released 433-qubit Osprey processor. Plans to reach 100,000 qubits by 2026.",
        },
    ]
    
    try:
        synthesis, stats = await parallel_synthesize_documents(
            query="quantum computing advances 2024",
            documents=documents,
            max_concurrent=3,
            timeout=5.0,
            token_limit=80,
        )
        
        print(f"\n📊 Stats:")
        print(f"  Success rate: {stats['success_rate']:.0%}")
        print(f"  Duration: {stats['total_duration_ms']}ms")
        print(f"  Speedup: {stats['speedup']:.1f}x")
        print(f"\n📝 Synthesis:")
        print(synthesis)
        
    except Exception as e:
        print(f"❌ Test failed: {e}")
    
    print("\n" + "="*80)


if __name__ == "__main__":
    # Run test
    asyncio.run(_test_parallel_synthesis())
