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
- Implemented load and performance test coverage for throughput, end-to-end latency, and idle listener memory footprint (`tests/load/test_backfill_throughput.py`, `tests/load/test_latency.py`, `tests/load/test_memory.py`)
- Added DLQ persistence in classification flow for unrecoverable classification failures to satisfy PRD error-handling expectations (`gmail_sorter/classifier/engine.py`)
- Expanded configuration schema coverage for PRD gap remediation Task 18.1:
  - Added typed runtime controls in `gmail_sorter/config/models.py` for sender allow/block lists, backfill progress interval, Pub/Sub push endpoint and port, observability ports, DB retention days, and alert webhook URL
  - Updated default `config.yaml` with corresponding runtime-control fields and defaults
  - Expanded config model/loader unit coverage in `tests/unit/config/test_models.py` and `tests/unit/config/test_loader.py` for new defaults and invalid-value validation
- Completed final integration and packaging checks with containerized verification for installability, full test suite execution, configuration validation, Docker build, and prompt rendering
- Added packaging and test hardening updates:
  - Explicit setuptools package discovery for `gmail_sorter` in `pyproject.toml`
  - HTTP/2 dependency support with `h2>=4.1` in `requirements.txt`
  - Docker runtime package installation so the `gmail-sorter` entry point is available in built images
  - Test package `__init__.py` markers to avoid duplicate test module import collisions
  - Expanded test coverage for config loader, CLI wiring, and LLM client error/logging branches
- Default configuration and prompt template copied from the PRD
- Deployment artifacts (`Dockerfile`, `gmail_sorter.service`)

PRD verification was re-run on April 15, 2026 and found unresolved requirement gaps. Implementation is in active remediation mode, tracked in `PLAN.md` Task 18. Task 18.1 is complete and Task 18.2 is next.

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

7. Run load and performance tests:

```bash
python -m pytest tests/load/
```

## Usage

### Authentication

First, authenticate with Gmail using OAuth 2.0:

```bash
gmail-sorter auth
```

This opens a browser flow. The token is saved to `token.json` (configurable via `gmail.token_path`).

### Running the Service

Start the real-time Pub/Sub listener to classify new emails:

```bash
gmail-sorter run
```

Options:
- `--dry-run` - Log classifications without applying Gmail labels
- `--log-level DEBUG` - Enable debug logging
- `--config /path/to/config.yaml` - Use custom config file
- `--backfill` - Run backfill alongside the listener

### Running Backfill

Process all existing emails in the mailbox (one-time operation):

```bash
gmail-sorter backfill
```

### Validating Configuration

Check if config.yaml is valid:

```bash
gmail-sorter validate-config
```

### Viewing Statistics

Print classification statistics from the local database:

```bash
gmail-sorter stats
```

## Containerized Setup

### Building the Image

```bash
docker build -t gmail-sorter .
```

### Running the Container

```bash
docker run -d \
  --name gmail-sorter \
  -e GITHUB_COPILOT_API_KEY=your_api_key \
  -v $(pwd)/config.yaml:/app/config.yaml:ro \
  -v $(pwd)/credentials.json:/app/credentials.json:ro \
  -v $(pwd)/token.json:/app/token.json \
  -v $(pwd)/gmail_sorter.db:/app/gmail_sorter.db \
  gmail-sorter
```

The image exposes:
- Port 8080 - Health check endpoint
- Port 9090 - Prometheus metrics endpoint

### Volumes

- `/app/config.yaml` - Configuration file (mount as read-only)
- `/app/credentials.json` - OAuth credentials
- `/app/token.json` - OAuth token (persist to retain authentication)
- `/app/gmail_sorter.db` - SQLite database

### Dockerfile Entrypoint

The container runs `gmail-sorter run` by default. Override to run other commands:

```bash
docker run gmail-sorter backfill
docker run gmail-sorter validate-config
docker run gmail-sorter stats
```

## Roadmap

Plan execution has been reopened for PRD gap remediation. See `PLAN.md` execution status and Task 18 for the active implementation queue.
