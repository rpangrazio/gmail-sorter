# Stage 1: Build
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

# Install project package and CLI entry point
RUN pip install --no-cache-dir .

# Create non-root user
RUN useradd --create-home appuser
USER appuser

# Environment variables for LLM provider
ENV OPENAI_API_KEY=${OPENAI_API_KEY:-}
ENV LLM_BASE_URL=${LLM_BASE_URL:-}

EXPOSE 8080 9090

# Health check endpoint (see 14.3)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

ENTRYPOINT ["gmail-sorter"]
CMD ["run"]
