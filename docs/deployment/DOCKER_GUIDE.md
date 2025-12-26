# QuantumDev Docker Deployment Guide

This guide covers the complete Docker containerization setup for QuantumDev, including multi-stage builds, orchestration, and deployment procedures.

## Table of Contents

- [Overview](#overview)
- [Quick Start](#quick-start)
- [Architecture](#architecture)
- [Dockerfiles](#dockerfiles)
- [Docker Compose](#docker-compose)
- [Deployment Scripts](#deployment-scripts)
- [Configuration](#configuration)
- [Health Checks](#health-checks)
- [Monitoring](#monitoring)
- [Backup and Recovery](#backup-and-recovery)
- [Troubleshooting](#troubleshooting)

## Overview

QuantumDev uses Docker for consistent deployment across environments. The setup includes:

- **Multi-stage Dockerfiles** for optimized image sizes (<500MB)
- **Docker Compose** for full-stack orchestration
- **Health checks** for reliability
- **Non-root user** execution for security
- **Persistent volumes** for data safety

### Services

| Service | Description | Port |
|---------|-------------|------|
| api | FastAPI backend | 8081 |
| telegram-bot | Telegram bot service | - |
| redis | Cache layer | 6379 |
| chromadb | Vector database | 8000 |
| prometheus | Metrics collection | 9090 |
| grafana | Dashboards | 3000 |

## Quick Start

### Development Environment

```bash
# Clone the repository
cd quantumdev

# Copy environment file
cp .env.example .env
# Edit .env with your configuration

# Start development environment
./scripts/docker_deploy.sh dev

# Check status
./scripts/docker_deploy.sh status
```

### Production Environment

```bash
# Build images
./scripts/docker_build.sh -t v1.0.0 all

# Deploy production
./scripts/docker_deploy.sh prod

# Monitor logs
./scripts/docker_logs.sh -f all
```

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                        Frontend Network                       │
│  ┌──────────────┐    ┌─────────────────┐                    │
│  │   External   │    │   telegram-bot  │                    │
│  │   Clients    │    │                 │                    │
│  └──────┬───────┘    └────────┬────────┘                    │
│         │                     │                              │
│         ▼                     ▼                              │
│  ┌──────────────────────────────┐                           │
│  │         api (8081)           │                           │
│  │     FastAPI Backend          │                           │
│  └──────────────┬───────────────┘                           │
└─────────────────│───────────────────────────────────────────┘
                  │
┌─────────────────│───────────────────────────────────────────┐
│                 │          Backend Network                   │
│         ┌───────┴───────┐                                   │
│         ▼               ▼                                   │
│  ┌──────────┐    ┌───────────┐    ┌────────────┐           │
│  │  redis   │    │ chromadb  │    │ prometheus │           │
│  │  (6379)  │    │  (8000)   │    │   (9090)   │           │
│  └──────────┘    └───────────┘    └─────┬──────┘           │
│                                         │                   │
│                                   ┌─────▼──────┐           │
│                                   │  grafana   │           │
│                                   │   (3000)   │           │
│                                   └────────────┘           │
└─────────────────────────────────────────────────────────────┘
```

## Dockerfiles

### Main API Dockerfile

The main `Dockerfile` uses multi-stage builds:

```dockerfile
# Stage 1: Builder
FROM python:3.10-slim AS builder
# Install dependencies

# Stage 2: Runtime
FROM python:3.10-slim AS runtime
# Copy only what's needed
```

**Key features:**
- Python 3.10-slim base image
- Non-root user (uid 1000)
- Health checks configured
- Optimized layer caching

### Service-Specific Dockerfiles

| File | Purpose |
|------|---------|
| `Dockerfile` | FastAPI API server |
| `Dockerfile.bot` | Telegram bot service |
| `Dockerfile.worker` | Background task workers |

## Docker Compose

### Files

| File | Purpose |
|------|---------|
| `docker-compose.yml` | Base configuration |
| `docker-compose.prod.yml` | Production overrides |
| `docker-compose.dev.yml` | Development overrides |
| `docker-compose.monitoring.yml` | Monitoring stack |
| `docker-compose.test.yml` | Test environment |

### Usage

```bash
# Development
docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Production
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d

# Monitoring only
docker-compose -f docker-compose.monitoring.yml up -d
```

### Resource Limits (Production)

| Service | CPU | Memory |
|---------|-----|--------|
| api | 2.0 | 4GB |
| telegram-bot | 0.5 | 512MB |
| redis | 1.0 | 1GB |
| chromadb | 1.0 | 2GB |
| prometheus | 0.5 | 1GB |
| grafana | 0.5 | 512MB |

## Deployment Scripts

### docker_build.sh

Build Docker images:

```bash
# Build all images
./scripts/docker_build.sh

# Build with specific tag
./scripts/docker_build.sh -t v1.0.0

# Build specific service
./scripts/docker_build.sh api

# Build and push to registry
./scripts/docker_build.sh --push -r myregistry.com -t v1.0.0 all
```

### docker_deploy.sh

Deploy the application:

```bash
# Deploy development environment
./scripts/docker_deploy.sh dev

# Deploy production environment
./scripts/docker_deploy.sh prod

# Stop all services
./scripts/docker_deploy.sh stop

# Restart services
./scripts/docker_deploy.sh restart

# Check status
./scripts/docker_deploy.sh status
```

### docker_logs.sh

View and manage logs:

```bash
# View all logs
./scripts/docker_logs.sh

# Follow API logs
./scripts/docker_logs.sh api -f

# View last 500 lines
./scripts/docker_logs.sh bot -n 500

# Logs from last hour
./scripts/docker_logs.sh all --since 1h

# Export logs
./scripts/docker_logs.sh --export ./logs_export
```

### docker_backup.sh

Backup persistent data:

```bash
# Backup all volumes
./scripts/docker_backup.sh

# Backup specific service
./scripts/docker_backup.sh redis

# Restore from backup
./scripts/docker_backup.sh restore backups/redis_20240101.tar.gz redis-data

# List backups
./scripts/docker_backup.sh list

# Cleanup old backups
./scripts/docker_backup.sh cleanup -r 30
```

## Configuration

### Environment Variables

Create a `.env` file with required variables:

```env
# LLM Configuration
LLM_ENDPOINT=http://your-llm-endpoint
LLM_MODEL=qwen2.5-32b-awq
LLM_TEMPERATURE=0.7
LLM_MAX_TOKENS=512

# Telegram Bot
TELEGRAM_BOT_TOKEN=your-bot-token
TELEGRAM_ADMIN_ID=your-admin-id

# Security
ADMIN_TOKEN=your-admin-token
QUANTUM_SHARED_SECRET=your-shared-secret

# Grafana
GRAFANA_ADMIN_USER=admin
GRAFANA_ADMIN_PASSWORD=secure-password-here
```

### Volumes

Persistent data is stored in Docker volumes:

| Volume | Purpose | Backup Priority |
|--------|---------|-----------------|
| redis-data | Cache and rate limiting | Daily |
| chroma-data | Vector database | Daily |
| prometheus-data | Metrics history | Weekly |
| grafana-data | Dashboards | Weekly |
| app-logs | Application logs | Daily |

## Health Checks

### Endpoints

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `/healthz` | Basic health check | 200 OK with system info |
| `/readyz` | Readiness check | 200 if ready, 503 if not |

### /healthz Response

```json
{
  "ok": true,
  "model": "qwen2.5-32b-awq",
  "endpoints_to_try": [...],
  "reranker": {...},
  "redis": {...},
  "live_agents": {...}
}
```

### /readyz Response

```json
{
  "ready": true,
  "checks": {
    "redis": true,
    "llm_endpoint_configured": true,
    "chromadb": true
  },
  "timestamp": 1704067200
}
```

### Docker Health Checks

All services include health checks:

```yaml
healthcheck:
  test: ["CMD", "curl", "-f", "http://localhost:8081/healthz"]
  interval: 30s
  timeout: 10s
  retries: 3
  start_period: 30s
```

## Monitoring

### Prometheus Metrics

Access Prometheus at `http://localhost:9090`

Key metrics:
- `http_requests_total` - Request count
- `http_request_duration_seconds` - Request latency
- `quantumdev_cache_hits_total` - Cache hit rate
- `quantumdev_llm_requests_total` - LLM usage

### Grafana Dashboards

Access Grafana at `http://localhost:3000`

Pre-configured dashboards:
- QuantumDev Overview
- API Performance
- Cache Statistics
- LLM Usage

## Backup and Recovery

### Automated Backups

Set up a cron job for automated backups:

```bash
# Daily backup at 2 AM
0 2 * * * /path/to/quantumdev/scripts/docker_backup.sh all >> /var/log/quantumdev-backup.log 2>&1
```

### Recovery Procedure

1. Stop services:
   ```bash
   ./scripts/docker_deploy.sh stop
   ```

2. Restore volumes:
   ```bash
   ./scripts/docker_backup.sh restore backups/redis_20240101.tar.gz redis-data
   ./scripts/docker_backup.sh restore backups/chromadb_20240101.tar.gz chroma-data
   ```

3. Restart services:
   ```bash
   ./scripts/docker_deploy.sh prod
   ```

4. Verify health:
   ```bash
   ./scripts/docker_deploy.sh status
   ```

## Troubleshooting

### Common Issues

#### Services won't start

```bash
# Check logs
./scripts/docker_logs.sh all

# Check resource usage
docker stats

# Verify .env file exists
ls -la .env
```

#### API returns 503

```bash
# Check Redis
docker exec quantumdev-redis redis-cli ping

# Check ChromaDB
curl http://localhost:8000/api/v1/heartbeat

# Check LLM endpoint
curl -X POST http://localhost:8081/healthz
```

#### Out of disk space

```bash
# Clean up Docker resources
docker system prune -a

# Check volume sizes
docker system df -v
```

### Debug Mode

Run with debug logging:

```bash
# Set log level
export LOG_LEVEL=DEBUG

# Start with dev config
./scripts/docker_deploy.sh dev
```

### Container Access

```bash
# Access API container shell
docker exec -it quantumdev-api /bin/bash

# Access Redis CLI
docker exec -it quantumdev-redis redis-cli

# View real-time stats
docker stats
```

## Security Considerations

1. **Non-root user**: All containers run as non-root (uid 1000)
2. **Read-only filesystem**: Where possible, containers use read-only filesystems
3. **Network isolation**: Backend services are on an internal network
4. **No new privileges**: Containers cannot escalate privileges
5. **Resource limits**: Production containers have CPU/memory limits

### Secrets Management

For production, use Docker secrets or environment variables:

```bash
# Using Docker secrets
echo "my-secret-token" | docker secret create admin_token -

# Or environment variables (loaded from .env)
docker-compose --env-file .env.prod up -d
```

## Updating

### Rolling Update

```bash
# Build new images
./scripts/docker_build.sh -t v2.0.0 all

# Deploy with minimal downtime
docker-compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps api
```

### Full Restart

```bash
./scripts/docker_deploy.sh stop
./scripts/docker_build.sh -t v2.0.0 all
./scripts/docker_deploy.sh prod
```

## Additional Resources

- [Docker Documentation](https://docs.docker.com/)
- [Docker Compose Reference](https://docs.docker.com/compose/compose-file/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Grafana Documentation](https://grafana.com/docs/)
