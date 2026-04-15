# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added

- Initial Python package scaffold under `gmail_sorter/` with module placeholders.
- Test directory scaffold under `tests/` (`unit`, `integration`, `e2e`, `load`).
- Project packaging metadata in `pyproject.toml` and dependency list in `requirements.txt`.
- Default `config.yaml` copied from PRD Section 6.
- Default prompt template at `prompts/classify_email.j2` from PRD Section 12.2.
- Deployment assets: `Dockerfile`, `.dockerignore`, and `gmail_sorter.service`.
- `README.md` documenting current project status and development setup.
- Configuration model implementation in `gmail_sorter/config/models.py` with typed schema coverage and category uniqueness validation.
- Configuration loader implementation in `gmail_sorter/config/loader.py` with YAML parsing and structured validation error reporting.
- Unit tests for Task 2 in `tests/unit/config/test_models.py` covering happy path and validation failures.

### Changed

- Updated `PLAN.md` to align with PRD requirements, mark Task 2 complete, and set Task 3 as next.
- Updated `README.md` with Task 2 completion status and configuration test command.
