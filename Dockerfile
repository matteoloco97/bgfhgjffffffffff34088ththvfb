# ============================================================================
# QuantumDev - Multi-stage Dockerfile
# Production-ready container with optimized layers
# ============================================================================

# =============================================================================
# Stage 1: Builder - Install dependencies
# =============================================================================
FROM python:3.10-slim AS builder

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    gcc \
    g++ \
    libffi-dev \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Create virtual environment
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Install Python dependencies
WORKDIR /app
COPY requirements.txt .
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r requirements.txt

# =============================================================================
# Stage 2: Runtime - Minimal production image
# =============================================================================
FROM python:3.10-slim AS runtime

# Labels
LABEL org.opencontainers.image.title="QuantumDev API" \
      org.opencontainers.image.description="QuantumDev AI Assistant API Server" \
      org.opencontainers.image.version="1.0.0" \
      org.opencontainers.image.authors="QuantumDev Team"

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONFAULTHANDLER=1 \
    APP_HOME=/app \
    APP_USER=quantumdev \
    APP_UID=1000 \
    APP_GID=1000

# Install runtime dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    tesseract-ocr \
    tesseract-ocr-ita \
    tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/* \
    && apt-get clean

# Create non-root user
RUN groupadd --gid ${APP_GID} ${APP_USER} && \
    useradd --uid ${APP_UID} --gid ${APP_GID} --shell /bin/bash --create-home ${APP_USER}

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Set working directory
WORKDIR ${APP_HOME}

# Create necessary directories
RUN mkdir -p /app/logs /app/data /memory/chroma && \
    chown -R ${APP_USER}:${APP_USER} /app /memory

# Copy application code
COPY --chown=${APP_USER}:${APP_USER} . .

# Switch to non-root user
USER ${APP_USER}

# Expose port
EXPOSE 8081

# Health check (using wget for reliability)
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD wget --quiet --tries=1 --spider http://localhost:8081/healthz || exit 1

# Default command - run the FastAPI server
CMD ["uvicorn", "backend.quantum_api:app", "--host", "0.0.0.0", "--port", "8081"]
