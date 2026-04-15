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
- Retry utility in `gmail_sorter/utils/retry.py` with exponential backoff, optional jitter, and support for async and sync callables.
- MIME utility in `gmail_sorter/utils/mime.py` for recursive multipart extraction, HTML-to-text fallback, safe base64 decoding, truncation, and data URI sanitization.
- Domain filtering utility in `gmail_sorter/utils/security.py` implementing allowlist/blocklist logic for sender domains.
- Unit tests for Task 6 in `tests/unit/utils/test_retry.py`, `tests/unit/utils/test_mime.py`, and `tests/unit/utils/test_security.py`.
- Gmail API client implementation in `gmail_sorter/gmail/client.py` covering message retrieval/listing, label lifecycle, label application, watch registration, retry wrapping, and dry-run behavior.
- Label manager implementation in `gmail_sorter/gmail/labels.py` for startup label provisioning by category.
- Unit tests for Task 5 in `tests/unit/gmail/test_client.py` covering label reuse, dry-run suppression of API calls, and archive label modification payloads.
- Processor email parser implementation in `gmail_sorter/processor/email_parser.py` with `ProcessedEmail` normalization, header extraction, safe body sanitization, and truncation.
- Prompt builder implementation in `gmail_sorter/processor/prompt_builder.py` supporting inline/file Jinja2 templates and stable SHA-256 template hashing.
- Unit tests for Task 7 in `tests/unit/processor/test_email_parser.py` and `tests/unit/processor/test_prompt_builder.py` covering multipart extraction, HTML fallback, truncation, header mapping, template rendering, and template hashing.
- LLM client implementation in `gmail_sorter/llm/client.py` with Copilot chat completions integration, environment-based API key loading, configurable retry behavior, prompt/response logging controls, and structured error handling.
- LLM response parser implementation in `gmail_sorter/llm/response_parser.py` with JSON extraction fallback, category fallback routing, confidence clamping, and threshold enforcement.
- Unit tests for Task 8 in `tests/unit/llm/test_client.py` and `tests/unit/llm/test_response_parser.py` covering request payload shape, retry exhaustion behavior, API-key validation, prompt redaction, fallback behavior, malformed JSON handling, and confidence normalization.
- Classification idempotency implementation in `gmail_sorter/classifier/idempotency.py` with database and label-based duplicate detection.
- Classification engine orchestration in `gmail_sorter/classifier/engine.py` covering fetch, idempotency checks, sender policy gating, prompt generation, LLM response parsing, dry-run handling, label application, DB persistence, and metrics updates.
- Unit tests for Task 9 in `tests/unit/classifier/test_idempotency.py` and `tests/unit/classifier/test_engine.py` covering idempotent skip conditions, successful classification path, fallback routing, dry-run behavior, and early skip behavior without LLM calls.
- Pub/Sub watcher implementation in `gmail_sorter/pubsub/watcher.py` with Gmail watch registration, six-day renewal scheduling, and timer lifecycle management.
- Pub/Sub listener implementation in `gmail_sorter/pubsub/listener.py` with topic/subscription provisioning, pull and push mode support, Gmail history expansion, post-classification ack semantics, and per-message outcome logging.
- Gmail client history API support in `gmail_sorter/gmail/client.py` via `list_history` for resolving message IDs from Pub/Sub notifications.
- Unit tests for Task 10 in `tests/unit/pubsub/test_listener.py` and `tests/unit/pubsub/test_watcher.py` covering ack behavior, failure redelivery behavior, history pagination extraction, and renewal timer scheduling.
- Backfill engine implementation in `gmail_sorter/backfill/engine.py` with resumable state detection, paginated mailbox scanning, bounded async concurrency, progress logging, and interrupted/completed state persistence.
- Unit tests for Task 11 in `tests/unit/backfill/test_engine.py` covering full pagination processing, interrupted-state resume token handling, concurrency limits, and cancellation state updates.

### Changed

- Updated `PLAN.md` to align execution status with completed Tasks 5 and 6, and set Task 7 as next by dependency order.
- Updated `README.md` with current implementation status and expanded unit test commands.
- Updated `PLAN.md` to mark Task 7 complete and set Task 8 as next by dependency order.
- Updated `README.md` to include processor module/test coverage and Task 8 as the next implementation milestone.
- Updated `PLAN.md` after PRD and repository comparison to mark Task 8 complete and set Task 9 as the next task.
- Updated `README.md` to include LLM module/test coverage and Task 9 as the next implementation milestone.
- Updated `PLAN.md` after PRD and repository comparison to mark Task 9 complete and set Task 10 as the next task.
- Updated `README.md` to include classifier module/test coverage and Task 10 as the next implementation milestone.
- Updated `PLAN.md` after PRD and repository comparison to mark Task 10 complete and set Task 11 as the next task.
- Updated `README.md` to include Pub/Sub module/test coverage and Task 11 as the next implementation milestone.
- Updated `PLAN.md` after PRD and repository comparison to mark Task 11 complete and set Task 12 as the next task.
- Updated `README.md` to include backfill module/test coverage and Task 12 as the next implementation milestone.
