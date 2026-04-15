# Gmail Sorting System

Automated Gmail classification pipeline driven by a configurable LLM prompt and category mapping.

## Current Status

This repository currently contains:

- Product and planning docs (`PRD.md`, `PLAN.md`)
- Initial project scaffold and package layout
- Implemented configuration system (`gmail_sorter/config/models.py`, `gmail_sorter/config/loader.py`)
- Unit tests for configuration validation (`tests/unit/config/test_models.py`)
- Default configuration and prompt template copied from the PRD
- Deployment artifacts (`Dockerfile`, `gmail_sorter.service`)

Implementation tasks continue to be tracked in `PLAN.md`, with Task 3 (Database Layer) next.

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

3. Run configuration tests:

```bash
python -m pytest tests/unit/config/
```

4. Run test discovery:

```bash
python -m pytest tests/ --collect-only
```

## Roadmap

Implementation proceeds sequentially by task number in `PLAN.md`, with Task 3 (Database Layer) next.
