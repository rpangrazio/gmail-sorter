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
- Database schema implementation in `gmail_sorter/db/schema.py` with PRD-aligned tables and indexes.
- SQLite repository implementation in `gmail_sorter/db/repository.py` including classification upsert, backfill state handling, DLQ persistence, and stats querying.
- Unit tests for Task 3 in `tests/unit/db/test_repository.py` covering initialization, idempotent upsert, DLQ, backfill state, and stats.
- Gmail OAuth authenticator in `gmail_sorter/gmail/auth.py` with interactive auth flow, token refresh, keyring fallback behavior, scope validation, and 0600 token file permissions.
- Unit tests for Task 4 in `tests/unit/gmail/test_auth.py` covering chmod enforcement, refresh logic, and required scope validation.

### Changed

- Updated `PLAN.md` to align execution status with completed Tasks 3 and 4, and set Task 6 as next by dependency order.
- Updated `README.md` with current implementation status and expanded unit test commands.
