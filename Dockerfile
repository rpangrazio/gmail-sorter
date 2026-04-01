# =============================================================================
# Gmail AI Sorter — Dockerfile
# =============================================================================
#
# Multi-stage build:
#   Stage 1 (builder): Install Python dependencies into an isolated layer.
#   Stage 2 (runtime): Copy only the installed packages and source code.
#
# This keeps the final image small and free of build tools.
# =============================================================================

# ---------------------------------------------------------------------------
# Stage 1: Dependency builder
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS builder

WORKDIR /build

# Install build dependencies needed to compile some Python packages.
RUN apt-get update && apt-get install -y --no-install-recommends \
        gcc \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy only requirements first to leverage Docker layer caching.
# The wheels layer is rebuilt only when requirements.txt changes.
COPY requirements.txt .

RUN pip install --upgrade pip \
    && pip install --prefix=/install --no-cache-dir -r requirements.txt


# ---------------------------------------------------------------------------
# Stage 2: Runtime image
# ---------------------------------------------------------------------------
FROM python:3.12-slim AS runtime

# Metadata labels
LABEL org.opencontainers.image.title="Gmail AI Sorter"
LABEL org.opencontainers.image.description="AI-powered Gmail email sorter using Claude and Google Cloud Pub/Sub"
LABEL org.opencontainers.image.source="https://github.com/rpangrazio/gmail-sorter"

# Create a non-root user for security.
RUN groupadd --gid 1000 sorter \
    && useradd --uid 1000 --gid sorter --no-create-home sorter

WORKDIR /app

# Copy installed packages from builder stage.
COPY --from=builder /install /usr/local

# Copy application source code.
COPY src/ ./src/
COPY config/ ./config/

# Create data directory (will be overridden by Docker volume mount).
RUN mkdir -p /data /credentials \
    && chown -R sorter:sorter /app /data /credentials

# Switch to non-root user.
USER sorter

# Environment variables with sensible defaults.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    GOOGLE_CREDENTIALS_PATH=/credentials/credentials.json \
    GOOGLE_TOKEN_PATH=/data/token.json \
    STATE_FILE_PATH=/data/state.json \
    SQLITE_DB_PATH=/data/gmail_sorter.db \
    DATABASE_URL="" \
    CONFIG_PATH=/app/config/config.yaml

# Health check: verify the Python module can be imported without errors.
HEALTHCHECK --interval=60s --timeout=10s --start-period=30s --retries=3 \
    CMD python -c "from src.config_loader import load_config; print('OK')" || exit 1

# Default command: run the sorter agent.
CMD ["python", "-m", "src.main"]
