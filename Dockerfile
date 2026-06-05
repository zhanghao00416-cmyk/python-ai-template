# syntax=docker/dockerfile:1

# =============================================================================
# Builder stage — install dependencies
# =============================================================================
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install --no-cache-dir --user -e ".[dev]"

# =============================================================================
# Runtime stage — minimal image
# =============================================================================
FROM python:3.11-slim AS runtime

# Create non-root user
RUN groupadd -r appgroup && useradd -r -g appgroup appuser

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /home/appuser/.local
ENV PATH=/home/appuser/.local/bin:$PATH

# Copy application code
COPY --chown=appuser:appgroup app ./app
COPY --chown=appuser:appgroup configs ./configs
COPY --chown=appuser:appgroup prompts ./prompts
COPY --chown=appuser:appgroup alembic.ini .
COPY --chown=appuser:appgroup migrations ./migrations
COPY --chown=appuser:appgroup pyproject.toml .

# Create secrets directory
RUN mkdir -p /run/secrets && chown appuser:appgroup /run/secrets

# Switch to non-root user
USER appuser

EXPOSE 6006

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:6006/api/v1/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "6006"]
