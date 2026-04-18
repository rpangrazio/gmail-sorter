# Gmail Sorting System

Automated Gmail classification pipeline driven by a configurable LLM prompt and category mapping.

For detailed project status and implementation progress, see [CURRENT_STATUS.md](CURRENT_STATUS.md).

## Project Structure

- `gmail_sorter/` - source package modules
- `tests/` - unit, integration, e2e, and load test directories
- `prompts/` - Jinja2 prompt templates
- `config.yaml` - default application configuration
- `data/` - runtime data directory for config, credentials, tokens, and database (see `data/config.yaml`)

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

### Prerequisites

Before running gmail-sorter, you need:

1. **Python 3.11+** virtual environment
2. **Gmail OAuth credentials** (`credentials.json`) from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
3. **LLM API key** (configured in `config.yaml` or via `OPENAI_API_KEY` environment variable)
4. **Pub/Sub topic and subscription** (for real-time processing) - create via Google Cloud Console or `gcloud`

### Installation

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
```

### Configuration

Create or edit `data/config.yaml`. The `data/` directory stores config, credentials, tokens, and database:

```yaml
gmail:
  credentials_path: ./data/credentials.json
  token_path: ./data/token.json

llm:
  provider: openai_compatible  # or "github_copilot"
  model: gpt-4o
  api_key_env: OPENAI_API_KEY
  base_url: https://api.openai.com  # required for openai_compatible

pubsub:
  project_id: your-gcp-project
  topic: gmail-sorter-topic
  subscription: gmail-sorter-sub

classification:
  categories:
    - Work
    - Personal
    - Notifications
    - Spam
```

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
- `--config /path/to/data/config.yaml` - Use custom config file
- `--backfill` - Run backfill alongside the listener

### Running Backfill

Process all existing emails in the mailbox (one-time operation):

```bash
gmail-sorter backfill
```

Options:
- `--resume` - Resume from last checkpoint
- `--concurrency N` - Process N emails concurrently (default: 5)
- `--config /path/to/data/config.yaml` - Use custom config file

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

Options:
- `--since YYYY-MM-DD` - Filter stats since date
- `--until YYYY-MM-DD` - Filter stats until date

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `OPENAI_API_KEY` | LLM API key (required) | - |
| `LLM_BASE_URL` | Base URL for OpenAI-compatible provider | Configured in config.yaml |
| `GMAIL_CREDENTIALS_PATH` | OAuth credentials path | `credentials.json` |
| `GMAIL_TOKEN_PATH` | OAuth token path | `token.json` |
| `CONFIG_PATH` | Config file path | `data/config.yaml` |

### Running the Container

```bash
docker run -d \
  --name gmail-sorter \
  -e OPENAI_API_KEY=your_api_key \
  -e LLM_BASE_URL=https://api.openai.com \
  -v $(pwd)/data:/app/data \
  gmail-sorter
```

### Building the Image

```bash
docker build -t gmail-sorter .
```

The image exposes:
- Port 8080 - Health check endpoint
- Port 9090 - Prometheus metrics endpoint

### Volumes

- `/app/data` - Data directory containing config.yaml, credentials.json, token.json, and gmail_sorter.db

### Dockerfile Entrypoint

The container runs `gmail-sorter run` by default. Override to run other commands:

```bash
docker run gmail-sorter backfill
docker run gmail-sorter validate-config
docker run gmail-sorter stats
```

## Roadmap

Plan execution has been reopened for PRD gap remediation. See `PLAN.md` execution status and Task 18 for the active implementation queue.
