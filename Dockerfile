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

RUN pip install --no-cache-dir .

RUN useradd --create-home appuser
USER appuser

ENV APP_DIR=/app/data
# NOTE: Do NOT bake secrets or provider URLs into the image at build time.
# Provide the LLM API key and base URL at container runtime, e.g.:
#   docker run -e LLM_API_KEY="sk-..." -e LLM_BASE_URL="https://api.example.com/v1" \
#     -e LLM_API_KEY_ENV=OPENAI_API_KEY -v $(pwd)/data:/app/data gmail-sorter

RUN mkdir -p $APP_DIR

EXPOSE 8080 9090

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

ENTRYPOINT ["gmail-sorter"]
CMD ["run"]
