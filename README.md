# Gmail Sorting System

Automated Gmail classification pipeline driven by a configurable LLM prompt and category mapping.

For detailed project status and implementation progress, see [CURRENT_STATUS.md](CURRENT_STATUS.md).

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

### Prerequisites

Before running gmail-sorter, you need:

1. **Python 3.11+** virtual environment
2. **Gmail OAuth credentials** (`credentials.json`) from [Google Cloud Console](https://console.cloud.google.com/apis/credentials)
3. **LLM API key** (configured in `config.yaml` or via `GITHUB_COPILOT_API_KEY` environment variable)
4. **Pub/Sub topic and subscription** (for real-time processing) - create via Google Cloud Console or `gcloud`

### Installation

```bash
pip install -r requirements.txt
pip install -e ".[dev]"
```

### Configuration

Create or edit `config.yaml`:

```yaml
gmail:
  credentials_path: credentials.json
  token_path: token.json

llm:
  provider: github_copilot
  api_key: your_api_key_here

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
- `--config /path/to/config.yaml` - Use custom config file
- `--backfill` - Run backfill alongside the listener

### Running Backfill

Process all existing emails in the mailbox (one-time operation):

```bash
gmail-sorter backfill
```

Options:
- `--resume` - Resume from last checkpoint
- `--concurrency N` - Process N emails concurrently (default: 5)
- `--config /path/to/config.yaml` - Use custom config file

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
| `GITHUB_COPILOT_API_KEY` | LLM API key | Configured in config.yaml |
| `GMAIL_CREDENTIALS_PATH` | OAuth credentials path | `credentials.json` |
| `GMAIL_TOKEN_PATH` | OAuth token path | `token.json` |
| `CONFIG_PATH` | Config file path | `config.yaml` |

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
