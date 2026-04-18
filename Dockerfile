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
ENV OPENAI_API_KEY=${OPENAI_API_KEY:-}
ENV LLM_BASE_URL=${LLM_BASE_URL:-}

RUN mkdir -p $APP_DIR

EXPOSE 8080 9090

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

ENTRYPOINT ["gmail-sorter"]
CMD ["run"]
