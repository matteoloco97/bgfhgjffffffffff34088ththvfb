#!/usr/bin/env python3
"""
scripts/demo_multi_engine_search.py
====================================
Demonstrates usage of multi-engine search aggregator.

Usage:
    python scripts/demo_multi_engine_search.py "your search query"
"""

import asyncio
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.multi_search_aggregator import aggregate_multi_engine


async def main():
    """Main demo function."""
    if len(sys.argv) < 2:
        print("Usage: python scripts/demo_multi_engine_search.py 'your search query'")
        sys.exit(1)
    
    query = " ".join(sys.argv[1:])
    print(f"🔍 Searching for: {query}")
    print("=" * 80)
    
    # Configure which engines to use
    # Default: uses SEARCH_ENGINES_ENABLED env var or ["duckduckgo", "brave", "bing"]
    # You can override here:
    # engines = ["duckduckgo"]  # Only use DuckDuckGo
    # engines = ["brave", "duckduckgo"]  # Use Brave + DuckDuckGo
    engines = None  # Use default from env
    
    # Run multi-engine search
    results = await aggregate_multi_engine(
        query=query,
        engines=engines,
        max_results=10  # Get top 10 unique results
    )
    
    print(f"\n✅ Found {len(results)} unique results:\n")
    
    for i, result in enumerate(results, 1):
        title = result.get("title", "N/A")
        url = result.get("url", "N/A")
        snippet = result.get("snippet", "")
        source = result.get("source", "unknown")
        
        print(f"{i}. {title}")
        print(f"   URL: {url}")
        print(f"   Source: {source}")
        if snippet:
            # Truncate snippet to 150 chars
            snippet_preview = snippet[:150] + "..." if len(snippet) > 150 else snippet
            print(f"   Snippet: {snippet_preview}")
        print()
    
    if not results:
        print("ℹ️  No results found. This might be because:")
        print("   - Network is unavailable")
        print("   - Search engines are disabled via environment variables")
        print("   - Brave API key is missing (if Brave is enabled)")
        print("\n💡 To enable Brave Search, set these environment variables:")
        print("   export BRAVE_SEARCH_API_KEY='your-api-key-here'")
        print("   export BRAVE_SEARCH_ENABLED='1'")


if __name__ == "__main__":
    # Run async main
    asyncio.run(main())
