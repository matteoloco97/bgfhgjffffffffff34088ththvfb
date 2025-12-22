#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scripts/run_autobug.py — CLI for AutoBug Health Checks

Run health checks from the command line and display results in a human-friendly format.
Can also output JSON for integration with monitoring tools.

Usage:
    python scripts/run_autobug.py              # Human-readable output
    python scripts/run_autobug.py --json       # JSON output
    python scripts/run_autobug.py --verbose    # Detailed output
"""

import os
import sys
import json
import argparse
from typing import Dict, Any

# Add project root to path
ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core.autobug import run_autobug_checks


def format_latency(ms: float) -> str:
    """Format latency in a human-readable way."""
    if ms < 1:
        return f"{ms:.2f}ms"
    elif ms < 1000:
        return f"{ms:.0f}ms"
    else:
        return f"{ms/1000:.2f}s"


def print_check_result(check: Dict[str, Any], verbose: bool = False) -> None:
    """Print a single check result."""
    name = check.get("name", "unknown")
    ok = check.get("ok", False)
    latency = check.get("latency_ms", 0)
    error = check.get("error")
    details = check.get("details", {})
    
    # Status symbol
    symbol = "✓" if ok else "✗"
    
    # Format the line
    status = f"{symbol} {name:20s} {format_latency(latency):>10s}"
    
    if ok:
        print(f"\033[92m{status}\033[0m")  # Green
        if verbose and details:
            for key, value in details.items():
                print(f"    {key}: {value}")
    else:
        print(f"\033[91m{status}\033[0m")  # Red
        if error:
            print(f"    Error: {error}")


def print_summary(result: Dict[str, Any], verbose: bool = False) -> None:
    """Print a summary of the AutoBug run."""
    summary = result.get("summary", {})
    total = summary.get("total", 0)
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    duration_ms = result.get("duration_ms", 0)
    ok = result.get("ok", False)
    
    print("\n" + "=" * 60)
    print("AutoBug Health Check Summary")
    print("=" * 60)
    
    print(f"\nTotal checks:  {total}")
    print(f"Passed:        \033[92m{passed}\033[0m")
    print(f"Failed:        \033[91m{failed}\033[0m")
    print(f"Duration:      {format_latency(duration_ms)}")
    
    if ok:
        print(f"\nOverall status: \033[92m✓ ALL CHECKS PASSED\033[0m")
    else:
        print(f"\nOverall status: \033[91m✗ SOME CHECKS FAILED\033[0m")
    
    if verbose:
        print(f"\nStarted at:  {result.get('started_at')}")
        print(f"Finished at: {result.get('finished_at')}")
        
        # Show system status if available
        system_status = result.get("system_status", {})
        if system_status and system_status.get("ok"):
            metrics = system_status.get("metrics", {})
            cpu = metrics.get("cpu", {})
            memory = metrics.get("memory", {})
            
            print("\nSystem Status:")
            if "percent" in cpu:
                print(f"  CPU:  {cpu['percent']}%")
            if "ram" in memory:
                ram = memory["ram"]
                print(f"  RAM:  {ram.get('percent')}% ({ram.get('used_gb')}GB / {ram.get('total_gb')}GB)")
    
    print("=" * 60 + "\n")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run AutoBug health checks for Jarvis AI system"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results in JSON format",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Show detailed information",
    )
    
    args = parser.parse_args()
    
    # Run the checks
    try:
        result = run_autobug_checks()
    except Exception as e:
        print(f"\033[91mError running AutoBug checks: {e}\033[0m", file=sys.stderr)
        return 1
    
    # Output results
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        # Human-readable output
        print("\n" + "=" * 60)
        print("AutoBug Health Checks")
        print("=" * 60 + "\n")
        
        checks = result.get("checks", [])
        for check in checks:
            print_check_result(check, verbose=args.verbose)
        
        print_summary(result, verbose=args.verbose)
    
    # Exit with appropriate code
    return 0 if result.get("ok", False) else 1


if __name__ == "__main__":
    sys.exit(main())
