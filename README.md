# Gmail Sorting System

Automated Gmail classification pipeline driven by a configurable LLM prompt and category mapping.

## Current Status

This repository currently contains:

- Product and planning docs (`PRD.md`, `PLAN.md`)
- Initial project scaffold and package layout
- Implemented configuration system (`gmail_sorter/config/models.py`, `gmail_sorter/config/loader.py`)
- Unit tests for configuration validation (`tests/unit/config/test_models.py`)
- Implemented database layer (`gmail_sorter/db/schema.py`, `gmail_sorter/db/repository.py`)
- Unit tests for database behavior (`tests/unit/db/test_repository.py`)
- Implemented Gmail OAuth authentication (`gmail_sorter/gmail/auth.py`)
- Unit tests for OAuth authentication (`tests/unit/gmail/test_auth.py`)
- Implemented shared utilities (`gmail_sorter/utils/retry.py`, `gmail_sorter/utils/mime.py`, `gmail_sorter/utils/security.py`)
- Unit tests for utility helpers (`tests/unit/utils/`)
- Implemented Gmail API client and label manager (`gmail_sorter/gmail/client.py`, `gmail_sorter/gmail/labels.py`)
- Unit tests for Gmail client behavior (`tests/unit/gmail/test_client.py`)
- Implemented email processor and prompt builder (`gmail_sorter/processor/email_parser.py`, `gmail_sorter/processor/prompt_builder.py`)
- Unit tests for processor behavior (`tests/unit/processor/`)
- Implemented LLM client and response parser (`gmail_sorter/llm/client.py`, `gmail_sorter/llm/response_parser.py`)
- Unit tests for LLM behavior (`tests/unit/llm/`)
- Implemented classification engine and idempotency checks (`gmail_sorter/classifier/engine.py`, `gmail_sorter/classifier/idempotency.py`)
- Unit tests for classification engine behavior (`tests/unit/classifier/`)
- Implemented Pub/Sub watcher and listener (`gmail_sorter/pubsub/watcher.py`, `gmail_sorter/pubsub/listener.py`)
- Unit tests for Pub/Sub behavior (`tests/unit/pubsub/`)
- Implemented backfill engine with resume/concurrency handling (`gmail_sorter/backfill/engine.py`)
- Unit tests for backfill behavior (`tests/unit/backfill/test_engine.py`)
- Implemented observability modules for structured logging, Prometheus metrics, and health checks (`gmail_sorter/observability/logging.py`, `gmail_sorter/observability/metrics.py`, `gmail_sorter/observability/health.py`)
- Unit tests for observability behavior (`tests/unit/observability/`)
- Implemented Click CLI with global flags and commands (`run`, `backfill`, `validate-config`, `auth`, `stats`) in `gmail_sorter/cli.py`
- Unit tests for CLI command behavior (`tests/unit/test_cli.py`)
- Implemented integration test coverage for database, Gmail client behavior, LLM client behavior, and pipeline composition (`tests/integration/`)
- Implemented end-to-end test coverage for CLI `run` and `backfill` workflows (`tests/e2e/test_full_pipeline.py`, `tests/e2e/test_backfill.py`)
- Added DLQ persistence in classification flow for unrecoverable classification failures to satisfy PRD error-handling expectations (`gmail_sorter/classifier/engine.py`)
- Default configuration and prompt template copied from the PRD
- Deployment artifacts (`Dockerfile`, `gmail_sorter.service`)

Implementation tasks continue to be tracked in `PLAN.md`, with Task 16 (Load & Performance Tests) next.

## Project Structure

- `gmail_sorter/` - source package modules
- `tests/` - unit, integration, e2e, and load test directories
- `prompts/` - Jinja2 prompt templates
- `config.yaml` - default application configuration

## Local Development

1. Create and activate a Python 3.11+ virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
```

3. Run currently implemented unit tests:

```bash
python -m pytest tests/unit/config/
python -m pytest tests/unit/db/
python -m pytest tests/unit/gmail/
python -m pytest tests/unit/utils/
python -m pytest tests/unit/processor/
python -m pytest tests/unit/llm/
python -m pytest tests/unit/classifier/
python -m pytest tests/unit/pubsub/
python -m pytest tests/unit/backfill/
python -m pytest tests/unit/observability/
python -m pytest tests/unit/test_cli.py
```

4. Run test discovery:

```bash
python -m pytest tests/ --collect-only
```

5. Run integration tests:

```bash
python -m pytest tests/integration/
```

6. Run end-to-end tests:

```bash
python -m pytest tests/e2e/
```

## Roadmap

Implementation proceeds by dependency order in `PLAN.md`, with Task 16 (Load & Performance Tests) next.
