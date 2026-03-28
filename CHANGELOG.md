# Changelog

All notable changes to Gmail AI Sorter are documented in this file.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [Unreleased]

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

[Unreleased]: https://github.com/rpangrazio/gmail-sorter/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/rpangrazio/gmail-sorter/releases/tag/v1.0.0
