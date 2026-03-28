# Changelog

All notable changes to Gmail AI Sorter are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

---

## [1.1.0] — 2026-03-28

### Added

- **OpenAI provider support** — email classification can now use any
  OpenAI chat-completion model (default `gpt-4o`) in addition to Claude.

- `ai_provider` config field (`"anthropic"` | `"openai"`, default `"anthropic"`).

- `openai_model` config field (default `"gpt-4o"`).  Any model accepted by
  the target endpoint can be specified (e.g. `gpt-4o-mini`, `gpt-4-turbo`,
  Azure deployment names, OpenRouter slugs).

- `OPENAI_API_KEY` environment variable — required when `ai_provider = openai`.

- `OPENAI_BASE_URL` environment variable — optional base URL override for
  OpenAI-compatible third-party endpoints (Azure OpenAI, OpenRouter, Ollama, etc.).

- `openai>=1.30.0` added to `requirements.txt`.

### Changed

- **`src/classifier.py`** refactored into a provider abstraction:
  - New `BaseClassifier` abstract base class with shared `_parse_category()`
    and `_log_result()` helpers.
  - `AnthropicClassifier` — existing Claude logic moved here unchanged
    (prompt caching and adaptive thinking preserved).
  - `OpenAIClassifier` — new backend using `openai.OpenAI.chat.completions.create()`
    with `temperature=0` for deterministic output.
  - `create_classifier()` factory function selects the backend from config
    and validates that the required API key is present.

- **`src/main.py`** updated to use `create_classifier()` factory and
  `BaseClassifier` type annotation; logs the active provider and model at
  startup.

- **`src/config_loader.py`** adds `ai_provider`, `anthropic_model`, and
  `openai_model` fields to `Config`; validates `ai_provider` value.

- **`config/config.yaml`** documents the new `ai_provider`, `anthropic_model`,
  and `openai_model` fields with inline comments.

- **`.env.example`** documents `OPENAI_API_KEY` and `OPENAI_BASE_URL`.

---

## [1.0.0] — 2026-03-28

### Added

- **Gmail AI Sorter agent** — full initial implementation.

- **`src/main.py`** — Application entry point and orchestrator.
  - `--setup` flag for first-time OAuth2 authorization.
  - `--config` flag to specify an alternate config file path.
  - Background watch-renewal thread that renews the Gmail watch before
    it expires (every 6 days within the 7-day limit).
  - In-memory deduplication set (capacity 500) to prevent double-labelling
    when Pub/Sub delivers a notification more than once.
  - Graceful shutdown on `SIGINT` / `KeyboardInterrupt`.

- **`src/auth.py`** — Google OAuth2 authentication manager.
  - Interactive browser-based consent flow (falls back to console URL
    on headless systems).
  - Automatic token refresh on expiry using the stored refresh token.
  - Atomic token persistence to disk.

- **`src/gmail_client.py`** — Gmail REST API wrapper.
  - `get_profile()` — fetches user profile and bootstraps history cursor.
  - `ensure_watch()` — registers/renews Gmail push notification watch.
  - `list_new_messages()` — uses History API with pagination to return
    new inbox message IDs since the last cursor.
  - `get_message()` — fetches full message, extracts headers and decoded
    plain-text body (falls back to stripped HTML).
  - `apply_label()` — adds a label to a message.
  - Exponential backoff retry (up to 5 attempts) on HTTP 429 and 5xx.
  - `HistoryExpiredError` raised when the history cursor is too old;
    handled gracefully by resetting to the current historyId.

- **`src/pubsub_client.py`** — Cloud Pub/Sub pull subscriber.
  - `run_forever()` with optional `threading.Event` stop signal.
  - Batch acknowledgement after each pull cycle.
  - Handles `DeadlineExceeded` (normal empty-poll timeout) and
    `ServiceUnavailable` (transient network error) without crashing.
  - Base64 decoding of Pub/Sub message data to JSON notification payloads.

- **`src/classifier.py`** — Claude AI email classifier.
  - Uses `claude-opus-4-6` with adaptive thinking (`thinking: {type: "adaptive"}`).
  - System prompt built from config categories with prompt caching
    (`cache_control: {"type": "ephemeral"}`) to reduce per-email API cost.
  - Streaming via `client.messages.stream()` + `get_final_message()`.
  - Robust response parsing (handles punctuation, whitespace, embedded
    category names, and NONE/N/A/UNKNOWN responses).

- **`src/config_loader.py`** — YAML configuration loader and validator.
  - Required field validation with clear error messages.
  - Pub/Sub resource path format validation.
  - Duplicate category name detection.
  - Minimum description length enforcement.

- **`src/state_manager.py`** — Persistent state manager.
  - Stores Gmail history cursor (`historyId`) and watch expiry timestamp.
  - Atomic file writes (write-to-temp + rename) to prevent corruption.
  - `is_watch_expiring_soon(buffer_hours=24)` helper for renewal logic.

- **`src/label_manager.py`** — Gmail label cache and creator.
  - In-memory label name → label ID cache.
  - Lazy cache population on first use.
  - Automatic parent label creation for nested label paths (`AI-Sorted/Work`).
  - Handles HTTP 409 (label already exists) race conditions gracefully.

- **`config/config.yaml`** — Default configuration with six pre-defined
  categories: `github`, `work`, `finance`, `receipts`, `newsletters`,
  `personal`.

- **`Dockerfile`** — Multi-stage build (builder + runtime) for minimal image
  size.  Runs as a non-root user (`uid=1000`).  Includes a `HEALTHCHECK`.

- **`docker-compose.yml`** — Compose file with named volume for persistent
  state, read-only credential mount, live config bind-mount, resource limits,
  and JSON log rotation.

- **`scripts/setup_gcp.sh`** — Shell script that automates GCP setup:
  enables APIs, creates topic and subscription, grants IAM binding.

- **`README.md`** — Full setup, usage, configuration, troubleshooting, and
  security documentation.

- **`CHANGELOG.md`** — This file.

- **`.env.example`** — Template for the `.env` environment file.

- **`.gitignore`** — Excludes secrets, tokens, Python artifacts, and IDE files.

- **`requirements.txt`** — Pinned minimum versions for all dependencies.

[Unreleased]: https://github.com/rpangrazio/gmail-sorter/compare/v1.1.0...HEAD
[1.1.0]: https://github.com/rpangrazio/gmail-sorter/compare/v1.0.0...v1.1.0
[1.0.0]: https://github.com/rpangrazio/gmail-sorter/releases/tag/v1.0.0
