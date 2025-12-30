#!/usr/bin/env python3
"""
Manual test script to demonstrate WebRouter functionality.
Run this to see routing decisions for various queries.
"""

import sys
import os

# Add project root to path
_PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, _PROJECT_ROOT)

from core.web_router import get_web_router

def demo_webrouter():
    """Demonstrate WebRouter with various queries."""
    router = get_web_router(use_llm_classifier=False)
    
    # Test queries
    test_queries = [
        # Should trigger web (explicit keywords)
        "cerca su internet il prezzo di bitcoin",
        "search for latest news about AI",
        "dammi le fonti per questa notizia",
        
        # Should trigger web (time-sensitive)
        "prezzo bitcoin oggi",
        "meteo roma domani",
        "risultato milan juventus",
        "ultime notizie di politica",
        
        # Should NOT trigger web (general knowledge)
        "cos'è la fotosintesi",
        "spiega la teoria della relatività",
        "ciao come stai",
        "dimmi una barzelletta",
    ]
    
    print("=" * 80)
    print("WebRouter Demo - Routing Decisions")
    print("=" * 80)
    print()
    
    for query in test_queries:
        result = router.route(query)
        log_line = router.format_log(result)
        
        print(f"Query: {query}")
        print(f"  {log_line}")
        print()
    
    print("=" * 80)
    print("Demo complete!")
    print("=" * 80)

if __name__ == "__main__":
    demo_webrouter()
