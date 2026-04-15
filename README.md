# Gmail Sorting System

Automated Gmail classification pipeline driven by a configurable LLM prompt and category mapping.

## Current Status

This repository currently contains:

- Product and planning docs (`PRD.md`, `PLAN.md`)
- Initial project scaffold and package layout
- Default configuration and prompt template copied from the PRD
- Deployment artifacts (`Dockerfile`, `gmail_sorter.service`)

Core implementation tasks (configuration models, Gmail client, classifier engine, Pub/Sub integration, backfill, observability, and CLI behavior) are planned and tracked in `PLAN.md`.

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

3. Run test discovery:

```bash
python -m pytest tests/ --collect-only
```

## Roadmap

Implementation proceeds sequentially by task number in `PLAN.md`, with Task 2 (Configuration System) next.
