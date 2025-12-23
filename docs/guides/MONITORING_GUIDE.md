# QuantumDev Monitoring Guide

This guide provides comprehensive documentation for the Prometheus-based monitoring system integrated into QuantumDev.

## Table of Contents

1. [Overview](#overview)
2. [Quick Start](#quick-start)
3. [Architecture](#architecture)
4. [Metrics Reference](#metrics-reference)
5. [Grafana Dashboards](#grafana-dashboards)
6. [Alert Configuration](#alert-configuration)
7. [Troubleshooting](#troubleshooting)
8. [Advanced Configuration](#advanced-configuration)

## Overview

QuantumDev now includes comprehensive monitoring capabilities powered by:
- **Prometheus**: Metrics collection, storage, and alerting
- **Grafana**: Visualization and dashboarding
- **prometheus-fastapi-instrumentator**: Automatic FastAPI instrumentation
- **Custom metrics**: Application-specific performance tracking

### Key Features

- ✅ Automatic HTTP request/response metrics
- ✅ Custom business metrics (chat requests, web searches, cache hits)
- ✅ Latency percentiles (p50, p95, p99)
- ✅ Real-time monitoring dashboards
- ✅ Configurable alerting
- ✅ 30-day metrics retention
- ✅ Docker-based deployment

## Quick Start

### Prerequisites

- Docker and Docker Compose installed
- QuantumDev FastAPI application running
- Port 8081 accessible (for metrics scraping)
- Ports 3000 (Grafana) and 9090 (Prometheus) available

### Step 1: Install Python Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `prometheus-client>=0.19.0`
- `prometheus-fastapi-instrumentator>=6.1.0`

### Step 2: Start QuantumDev API

Make sure your FastAPI application is running on port 8081:

```bash
uvicorn backend.quantum_api:app --host 0.0.0.0 --port 8081 --reload
```

Verify the `/metrics` endpoint is accessible:

```bash
curl http://localhost:8081/metrics
```

You should see Prometheus-formatted metrics output.

### Step 3: Start Monitoring Stack

Launch Prometheus and Grafana using Docker Compose:

```bash
docker-compose -f docker-compose.monitoring.yml up -d
```

This starts:
- **Prometheus** at http://localhost:9090
- **Grafana** at http://localhost:3000

### Step 4: Access Grafana

1. Open http://localhost:3000 in your browser
2. Login with default credentials:
   - Username: `admin`
   - Password: `quantumdev2024` (⚠️ CHANGE IN PRODUCTION!)
3. The QuantumDev dashboard should be automatically loaded

### Step 5: Verify Metrics Collection

1. Open Prometheus at http://localhost:9090
2. Go to Status → Targets
3. Verify `quantumdev-api` target is UP
4. Query a metric (e.g., `chat_requests_total`) in the Prometheus UI

## Architecture

```
┌─────────────────┐
│  QuantumDev API │ :8081
│  (FastAPI)      │
└────────┬────────┘
         │ /metrics endpoint
         │ (Prometheus format)
         ↓
┌─────────────────┐
│   Prometheus    │ :9090
│  (scrapes every │
│    15 seconds)  │
└────────┬────────┘
         │ PromQL queries
         ↓
┌─────────────────┐
│     Grafana     │ :3000
│  (dashboards &  │
│  visualization) │
└─────────────────┘
```

## Metrics Reference

### Counter Metrics

Counters are monotonically increasing values (never decrease).

#### `chat_requests_total`
Total number of chat requests processed.

**Labels:**
- `endpoint`: The API endpoint (e.g., `/chat`, `/chat/stream`)
- `status`: Request status (`success`, `error`)

**Example queries:**
```promql
# Request rate (requests per second)
rate(chat_requests_total[5m])

# Total requests by endpoint
sum(chat_requests_total) by (endpoint)

# Error rate
rate(chat_requests_total{status="error"}[5m])
```

#### `web_searches_total`
Total number of web search requests.

**Labels:**
- `search_type`: Type of search (`standard`, `deep`, `general`)
- `status`: Request status (`success`, `error`)

**Example queries:**
```promql
# Search rate
rate(web_searches_total[5m])

# Deep search percentage
100 * sum(rate(web_searches_total{search_type="deep"}[5m])) / sum(rate(web_searches_total[5m]))
```

#### `cache_hits_total` / `cache_misses_total`
Cache hit and miss counts.

**Labels:**
- `cache_type`: Type of cache (`redis`, `multi_level`, `semantic`)

**Example queries:**
```promql
# Cache hit rate
100 * sum(rate(cache_hits_total[5m])) / (sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m])))
```

#### `llm_requests_total`
Total LLM API requests.

**Labels:**
- `model`: LLM model used (e.g., `gpt-4`, `gpt-3.5-turbo`)
- `status`: Request status (`success`, `error`)

#### `errors_total`
Total error count.

**Labels:**
- `endpoint`: API endpoint where error occurred
- `error_type`: Type of error

### Histogram Metrics

Histograms track distributions of values (with configurable buckets).

#### `chat_latency_seconds`
Chat endpoint response latency distribution.

**Labels:**
- `endpoint`: The API endpoint

**Buckets:** [0.1, 0.5, 1.0, 2.0, 5.0, 10.0, 30.0] seconds

**Example queries:**
```promql
# p95 latency
histogram_quantile(0.95, sum(rate(chat_latency_seconds_bucket[5m])) by (le, endpoint))

# Average latency
rate(chat_latency_seconds_sum[5m]) / rate(chat_latency_seconds_count[5m])
```

#### `llm_synthesis_seconds`
LLM generation/synthesis latency.

**Labels:**
- `model`: LLM model used

#### `web_fetch_seconds`
Web content fetch latency.

**Labels:**
- `source_type`: Type of source being fetched

#### `cache_operation_seconds`
Cache operation latency.

**Labels:**
- `operation`: Type of operation (`get`, `set`, `delete`)
- `cache_type`: Type of cache

### Gauge Metrics

Gauges represent current values that can go up or down.

#### `active_sessions`
Current number of active chat sessions.

**Example queries:**
```promql
# Current active sessions
active_sessions

# Average over time
avg_over_time(active_sessions[5m])
```

#### `cache_size_bytes`
Current cache size in bytes.

**Labels:**
- `cache_type`: Type of cache

#### `llm_queue_size`
Number of requests waiting in LLM queue.

#### `memory_usage_bytes`
Current memory usage in bytes.

#### `redis_connections`
Number of active Redis connections.

### Summary Metrics

Summaries track distributions with pre-calculated quantiles.

#### `response_size_bytes`
Size of API responses in bytes.

**Labels:**
- `endpoint`: API endpoint

## Grafana Dashboards

### QuantumDev Main Dashboard

The main dashboard (`grafana/quantumdev_dashboard.json`) provides:

#### Panels:

1. **Chat Request Rate**
   - Shows requests per second for chat endpoints
   - Grouped by endpoint and status

2. **Web Search Rate**
   - Shows web search requests per second
   - Grouped by search type

3. **Chat Latency Percentiles**
   - p50, p95, p99 latencies for chat endpoints
   - Helps identify performance issues

4. **Cache Hit Rate**
   - Percentage of requests served from cache
   - Gauge visualization (green = good, red = poor)

5. **Error Rate**
   - Errors per second by endpoint and type
   - Critical for identifying issues

6. **Active Sessions**
   - Current number of active sessions
   - Gauge visualization

7. **LLM Synthesis Latency**
   - p50, p95, p99 for LLM operations
   - By model

8. **Web Fetch Latency**
   - p50, p95, p99 for web fetches
   - By source type

### Importing Custom Dashboards

To add custom dashboards:

1. Create a JSON file in `grafana/` directory
2. The dashboard will be auto-loaded on Grafana startup
3. Or import manually: Dashboards → Import → Upload JSON file

## Alert Configuration

### Creating Alert Rules

Prometheus supports alert rules defined in YAML files.

#### Example: High Error Rate Alert

Create `prometheus/alerts/api_alerts.yml`:

```yaml
groups:
  - name: quantumdev_api
    interval: 30s
    rules:
      - alert: HighErrorRate
        expr: |
          rate(errors_total[5m]) > 1
        for: 5m
        labels:
          severity: critical
        annotations:
          summary: "High error rate detected"
          description: "Error rate is {{ $value }} errors/second"

      - alert: HighLatency
        expr: |
          histogram_quantile(0.95, sum(rate(chat_latency_seconds_bucket[5m])) by (le)) > 5
        for: 5m
        labels:
          severity: warning
        annotations:
          summary: "High API latency detected"
          description: "P95 latency is {{ $value }} seconds"

      - alert: LowCacheHitRate
        expr: |
          100 * sum(rate(cache_hits_total[5m])) / (sum(rate(cache_hits_total[5m])) + sum(rate(cache_misses_total[5m]))) < 50
        for: 10m
        labels:
          severity: warning
        annotations:
          summary: "Low cache hit rate"
          description: "Cache hit rate is {{ $value }}%"
```

Update `prometheus.yml` to include the rules:

```yaml
rule_files:
  - "alerts/*.yml"
```

### Setting Up Alertmanager

For alert notifications (email, Slack, PagerDuty), use Alertmanager:

1. Uncomment the `alertmanager` service in `docker-compose.monitoring.yml`
2. Create `alertmanager/config.yml`:

```yaml
global:
  resolve_timeout: 5m

route:
  group_by: ['alertname']
  group_wait: 10s
  group_interval: 10s
  repeat_interval: 1h
  receiver: 'email'

receivers:
  - name: 'email'
    email_configs:
      - to: 'alerts@example.com'
        from: 'prometheus@example.com'
        smarthost: 'smtp.example.com:587'
        auth_username: 'prometheus@example.com'
        auth_password: 'password'
```

3. Restart the monitoring stack

## Troubleshooting

### Metrics endpoint not accessible

**Problem:** `/metrics` endpoint returns 404 or error.

**Solutions:**
1. Ensure `prometheus-fastapi-instrumentator` is installed
2. Check application logs for initialization errors
3. Verify the app is running: `curl http://localhost:8081/healthz`

### Prometheus not scraping metrics

**Problem:** Target shows as DOWN in Prometheus.

**Solutions:**
1. Check Prometheus logs: `docker logs quantumdev-prometheus`
2. Verify network connectivity: `docker exec quantumdev-prometheus wget -O- http://host.docker.internal:8081/metrics`
3. Check `prometheus.yml` target configuration
4. Ensure firewall allows connections

### Grafana dashboards not loading

**Problem:** Dashboards don't appear in Grafana.

**Solutions:**
1. Check provisioning configuration in `grafana/provisioning/`
2. Verify dashboard JSON is valid
3. Check Grafana logs: `docker logs quantumdev-grafana`
4. Manually import dashboard: Configuration → Dashboards → Import

### High memory usage in Prometheus

**Problem:** Prometheus container using too much memory.

**Solutions:**
1. Reduce retention period: Change `--storage.tsdb.retention.time=30d` to `7d` or `15d`
2. Reduce scrape frequency: Change `scrape_interval` from `15s` to `30s` or `60s`
3. Drop unused metrics using `metric_relabel_configs`

### Missing metrics data

**Problem:** Some metrics show no data.

**Solutions:**
1. Verify metrics are being generated: `curl http://localhost:8081/metrics | grep metric_name`
2. Check if code paths are being executed (generate some traffic)
3. Verify PromQL query syntax
4. Check time range in Grafana

## Advanced Configuration

### Custom Metrics in Code

To add custom metrics to your endpoints:

```python
from core.metrics import (
    track_chat_request,
    observe_chat_latency,
    track_cache_hit,
)
import time

@app.post("/my_endpoint")
async def my_endpoint():
    start = time.time()
    
    try:
        # Your logic here
        result = await some_operation()
        
        # Track success
        track_chat_request("/my_endpoint", "success")
        return result
        
    except Exception as e:
        # Track error
        track_chat_request("/my_endpoint", "error")
        raise
        
    finally:
        # Track latency
        observe_chat_latency("/my_endpoint", time.time() - start)
```

### Metric Decorators

Use decorators for cleaner code:

```python
from core.metrics import track_latency, track_request

@app.post("/my_endpoint")
@track_request("/my_endpoint", "chat")
@track_latency("chat", endpoint="/my_endpoint")
async def my_endpoint():
    # Your logic here
    pass
```

### Exposing Additional Metrics

To expose system metrics (CPU, memory, disk):

1. Uncomment `node-exporter` in `docker-compose.monitoring.yml`
2. Add to `prometheus.yml` scrape configs (already present but commented)
3. Create Grafana dashboard for system metrics

### Metrics Cardinality

**Important:** High cardinality (too many unique label combinations) can impact performance.

**Best practices:**
- Limit dynamic label values
- Don't use user IDs or session IDs as labels
- Use fixed label values when possible
- Aggregate high-cardinality data at the application level

### Production Considerations

#### Security

1. **Change default passwords:**
   - Update `GF_SECURITY_ADMIN_PASSWORD` in `docker-compose.monitoring.yml`
   
2. **Protect endpoints:**
   - Add authentication to `/metrics` endpoint
   - Use firewall rules to restrict access to ports 9090 and 3000
   
3. **Use HTTPS:**
   - Configure reverse proxy (nginx/traefik) with SSL
   - Update Grafana `GF_SERVER_ROOT_URL`

#### Scalability

1. **Prometheus federation:**
   - For multiple instances, use Prometheus federation
   - Central Prometheus aggregates from regional instances

2. **Long-term storage:**
   - Use Thanos or Cortex for long-term metrics storage
   - Prometheus is optimized for short-term (weeks)

3. **High availability:**
   - Run multiple Prometheus replicas
   - Use Alertmanager clustering

#### Backup and Restore

**Backup Prometheus data:**
```bash
docker run --rm -v quantumdev_prometheus-data:/data -v $(pwd)/backup:/backup busybox tar czf /backup/prometheus-backup.tar.gz -C /data .
```

**Backup Grafana data:**
```bash
docker run --rm -v quantumdev_grafana-data:/data -v $(pwd)/backup:/backup busybox tar czf /backup/grafana-backup.tar.gz -C /data .
```

**Restore:**
```bash
docker run --rm -v quantumdev_prometheus-data:/data -v $(pwd)/backup:/backup busybox tar xzf /backup/prometheus-backup.tar.gz -C /data
```

## Support and Resources

- **Prometheus Documentation:** https://prometheus.io/docs/
- **Grafana Documentation:** https://grafana.com/docs/
- **PromQL Tutorial:** https://prometheus.io/docs/prometheus/latest/querying/basics/
- **FastAPI Instrumentator:** https://github.com/trallnag/prometheus-fastapi-instrumentator

## Maintenance

### Regular Tasks

1. **Monitor disk usage** - Prometheus data grows over time
2. **Review and update alerts** - Adjust thresholds as needed
3. **Update dashboards** - Add new panels for new features
4. **Backup data** - Regular backups of Prometheus and Grafana data
5. **Update containers** - Keep Prometheus and Grafana up to date

### Updating Monitoring Stack

```bash
# Pull latest images
docker-compose -f docker-compose.monitoring.yml pull

# Restart with new images
docker-compose -f docker-compose.monitoring.yml up -d
```

---

**Last Updated:** 2024-12-23
**Version:** 1.0.0
