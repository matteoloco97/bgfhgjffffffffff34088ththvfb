# System Status & AutoBug Health Checks

This document describes the new system monitoring and health check endpoints added to the Jarvis API.

## Overview

Two new API endpoint groups have been added:

1. **System Status** (`/system/status`) - Real-time system metrics
2. **AutoBug Health Checks** (`/autobug/run`) - Comprehensive subsystem health checks

## System Status Endpoint

### `GET /system/status`

Returns real-time system metrics including CPU, RAM, disk, GPU (if available), and uptime.

**Example request:**
```bash
curl http://localhost:8000/system/status
```

**Example response:**
```json
{
  "ok": true,
  "timestamp": "2025-12-03T16:55:32.955088+00:00",
  "metrics": {
    "cpu": {
      "percent": 15.2,
      "count_logical": 8,
      "count_physical": 4,
      "per_core": [12.5, 18.3, 14.1, 16.7, ...],
      "load_average": {
        "1min": 1.23,
        "5min": 1.45,
        "15min": 1.67
      }
    },
    "memory": {
      "ram": {
        "total_gb": 16.0,
        "used_gb": 8.5,
        "available_gb": 7.5,
        "percent": 53.1
      },
      "swap": {
        "total_gb": 4.0,
        "used_gb": 0.2,
        "free_gb": 3.8,
        "percent": 5.0
      }
    },
    "disk": {
      "path": "/",
      "total_gb": 500.0,
      "used_gb": 250.0,
      "free_gb": 250.0,
      "percent": 50.0
    },
    "uptime": {
      "seconds": 345600.0,
      "boot_time_iso": "2025-11-29T12:00:00+00:00",
      "human_readable": "4d 0h 0m"
    },
    "gpu": {
      "available": true,
      "count": 1,
      "gpus": [
        {
          "index": 0,
          "name": "NVIDIA RTX 4090",
          "vram": {
            "total_gb": 24.0,
            "used_gb": 12.5,
            "free_gb": 11.5,
            "percent": 52.1
          },
          "utilization": {
            "gpu_percent": 75,
            "memory_percent": 52
          },
          "temperature_c": 65
        }
      ]
    }
  }
}
```

**Notes:**
- `ok` is `true` if basic CPU and RAM metrics were successfully collected
- GPU metrics are optional and only included if NVIDIA GPUs are detected
- All functions handle errors gracefully - errors are returned in the response, not raised

## AutoBug Health Checks Endpoint

### `POST /autobug/run`

Runs comprehensive health checks on all major subsystems and returns detailed results.

**Example request:**
```bash
curl -X POST http://localhost:8000/autobug/run
```

**Example response:**
```json
{
  "ok": true,
  "started_at": "2025-12-03T16:55:00.000000+00:00",
  "finished_at": "2025-12-03T16:55:05.123456+00:00",
  "duration_ms": 5123.45,
  "checks": [
    {
      "name": "system_status",
      "ok": true,
      "latency_ms": 201.5,
      "error": null,
      "details": {
        "cpu_percent": 15.2,
        "ram_percent": 53.1
      }
    },
    {
      "name": "redis",
      "ok": true,
      "latency_ms": 5.3,
      "error": null,
      "details": {
        "host": "localhost",
        "port": 6379,
        "db": 0
      }
    },
    {
      "name": "chroma",
      "ok": true,
      "latency_ms": 123.7,
      "error": null,
      "details": {
        "collection": "facts",
        "document_count": 42
      }
    },
    {
      "name": "web_search",
      "ok": true,
      "latency_ms": 1234.5,
      "error": null,
      "details": {
        "result_count": 3,
        "first_url": "https://en.wikipedia.org/wiki/Wikipedia"
      }
    },
    {
      "name": "llm",
      "ok": true,
      "latency_ms": 3456.2,
      "error": null,
      "details": {
        "response_length": 4,
        "sample": "pong"
      }
    }
  ],
  "summary": {
    "total": 5,
    "passed": 5,
    "failed": 0
  },
  "system_status": {
    "ok": true,
    "timestamp": "2025-12-03T16:55:05.123456+00:00",
    "metrics": { ... }
  }
}
```

### Health Checks Performed

1. **System Status** - Validates that system metrics can be collected
2. **Redis** - Tests Redis connectivity with SET/GET operations
3. **ChromaDB** - Tests ChromaDB connectivity and collection access
4. **Web Search** - Performs a test search query
5. **LLM** - Tests LLM inference with a simple ping/pong

### Check Results

Each check returns:
- `name`: Check identifier
- `ok`: Boolean indicating success/failure
- `latency_ms`: Time taken to perform the check
- `error`: Error message if check failed (null otherwise)
- `details`: Additional context about the check (optional)

### Summary

The `summary` section provides:
- `total`: Total number of checks executed
- `passed`: Number of successful checks
- `failed`: Number of failed checks

The overall `ok` field is `true` only if ALL checks passed.

## CLI Script

A command-line script is also available for manual health checks:

```bash
# Human-readable output
python scripts/run_autobug.py

# JSON output
python scripts/run_autobug.py --json

# Verbose output with details
python scripts/run_autobug.py --verbose
```

**Example output:**
```
============================================================
AutoBug Health Checks
============================================================

✓ system_status          201ms
✓ redis                    5ms
✓ chroma                 124ms
✓ web_search            1.23s
✓ llm                    3.46s

============================================================
AutoBug Health Check Summary
============================================================

Total checks:  5
Passed:        5
Failed:        0
Duration:      5.12s

Overall status: ✓ ALL CHECKS PASSED
============================================================
```

The script exits with code 0 if all checks pass, or 1 if any check fails, making it suitable for use in monitoring systems and cron jobs.

## Environment Variables

### System Status
No specific configuration required. Automatically detects available hardware.

### AutoBug Configuration

```bash
# Enable/disable AutoBug entirely
AUTOBUG_ENABLED=1                    # Default: 1 (enabled)

# Enable/disable individual checks
AUTOBUG_ENABLE_LLM=1                 # Default: 1
AUTOBUG_ENABLE_WEB_SEARCH=1          # Default: 1
AUTOBUG_ENABLE_REDIS=1               # Default: 1
AUTOBUG_ENABLE_CHROMA=1              # Default: 1
AUTOBUG_ENABLE_SYSTEM=1              # Default: 1

# Timeouts for individual checks (in seconds)
AUTOBUG_LLM_TIMEOUT_S=15.0           # Default: 15.0
AUTOBUG_WEB_TIMEOUT_S=10.0           # Default: 10.0
AUTOBUG_REDIS_TIMEOUT_S=5.0          # Default: 5.0
AUTOBUG_CHROMA_TIMEOUT_S=10.0        # Default: 10.0

# Redis connection (used by Redis check)
REDIS_HOST=localhost                 # Default: localhost
REDIS_PORT=6379                      # Default: 6379
REDIS_DB=0                           # Default: 0
```

## Error Handling

Both endpoints are designed to be **non-disruptive**:

1. They **never raise uncaught exceptions**
2. All errors are captured and returned in the response
3. Individual check failures don't prevent other checks from running
4. Missing dependencies are handled gracefully with informative error messages

## Use Cases

### System Monitoring
```bash
# Check system resources every 5 minutes
*/5 * * * * curl -s http://localhost:8000/system/status | jq '.metrics.memory.ram.percent'
```

### Health Checks
```bash
# Run comprehensive health checks
curl -X POST http://localhost:8000/autobug/run | jq '.ok'

# CLI with exit code for monitoring
python scripts/run_autobug.py || echo "Health checks failed!"
```

### Pre-deployment Validation
```bash
# Verify all systems operational before deployment
python scripts/run_autobug.py --json > health-check.json
```

## Integration with Existing Systems

The new endpoints integrate seamlessly with the existing Jarvis API:

- Use the same logging configuration
- Respect existing environment variables
- Don't modify or break existing endpoints
- Follow the same error handling patterns
- Use existing helper modules (Redis, ChromaDB, web search, LLM)

## Dependencies

New dependencies added to `requirements.txt`:

```
psutil>=5.9.0                # System monitoring (required)
nvidia-ml-py>=12.535.0       # GPU monitoring (optional)
```

Install with:
```bash
pip install -r requirements.txt
```
