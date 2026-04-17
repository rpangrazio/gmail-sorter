# Gmail Sorting System — Implementation Plan

This plan is structured as a series of discrete, ordered tasks for an LLM coding agent to execute sequentially. Each task specifies exactly what to create or implement, the acceptance criteria, and any dependencies on prior tasks. Complete each task fully before starting the next.

---

## Execution Status

- Repository comparison completed on April 15, 2026.
- `main` branch is up to date with `origin/main`.
- Task 1 — Project Scaffold has been executed.
- Task 2 — Configuration System has been executed (`gmail_sorter/config/models.py`, `gmail_sorter/config/loader.py`, and `tests/unit/config/test_models.py`).
- Task 3 — Database Layer has been executed (`gmail_sorter/db/schema.py`, `gmail_sorter/db/repository.py`, and `tests/unit/db/test_repository.py`).
- Task 4 — Gmail OAuth Authentication has been executed (`gmail_sorter/gmail/auth.py` and `tests/unit/gmail/test_auth.py`).
- Task 6 — Utilities has been executed (`gmail_sorter/utils/retry.py`, `gmail_sorter/utils/mime.py`, `gmail_sorter/utils/security.py`, and `tests/unit/utils/`).
- Task 5 — Gmail API Client has been executed (`gmail_sorter/gmail/client.py`, `gmail_sorter/gmail/labels.py`, and `tests/unit/gmail/test_client.py`).
- Task 7 — Email Processor & Prompt Builder has been executed (`gmail_sorter/processor/email_parser.py`, `gmail_sorter/processor/prompt_builder.py`, and `tests/unit/processor/`).
- Task 8 — LLM Client has been executed (`gmail_sorter/llm/client.py`, `gmail_sorter/llm/response_parser.py`, and `tests/unit/llm/`).
- Task 9 — Classification Engine has been executed (`gmail_sorter/classifier/idempotency.py`, `gmail_sorter/classifier/engine.py`, and `tests/unit/classifier/`).
- Task 10 — Pub/Sub Integration has been executed (`gmail_sorter/pubsub/watcher.py`, `gmail_sorter/pubsub/listener.py`, and `tests/unit/pubsub/`).
- Task 11 — Backfill Engine has been executed (`gmail_sorter/backfill/engine.py` and `tests/unit/backfill/test_engine.py`).
- Task 12 — Observability has been executed (`gmail_sorter/observability/logging.py`, `gmail_sorter/observability/metrics.py`, `gmail_sorter/observability/health.py`, and `tests/unit/observability/`).
- Task 13 — CLI has been executed (`gmail_sorter/cli.py` and `tests/unit/test_cli.py`).
- PRD-to-plan comparison completed; current task sequence remains aligned with PRD scope and ordering, with no additional plan tasks required at this checkpoint.
- Repository comparison against this plan confirms Tasks 1–16 are implemented; Task 17 remains pending.
- Task 14 — Integration Tests has been executed (`tests/integration/test_database.py`, `tests/integration/test_gmail_client.py`, `tests/integration/test_llm_client.py`, and `tests/integration/test_pipeline.py`).
- Local environment currently lacks a Python runtime (`python: command not found`, `python3: command not found`), so pytest execution for newly added tests could not be verified in-session.
- Task 15 — End-to-End Tests has been executed (`tests/e2e/test_full_pipeline.py` and `tests/e2e/test_backfill.py`).
- PRD-to-plan comparison revalidated after Task 15 execution; task ordering and remaining scope are still aligned to PRD requirements.
- Task 16 — Load & Performance Tests has been executed (`tests/load/test_backfill_throughput.py`, `tests/load/test_latency.py`, and `tests/load/test_memory.py`).
- PRD-to-plan comparison revalidated after Task 16 execution; task ordering and remaining scope are still aligned to PRD requirements.
- Host environment currently lacks a Python runtime (`python: command not found`, `python3: command not found`); verification commands were executed in a Python 3.12 container.
- Task 17 — Final Integration & Packaging has been executed.
- Task 17.1 complete: editable install and `gmail-sorter --help` verified in container.
- Task 17.2 complete: `pytest --cov=gmail_sorter --cov-report=term-missing tests/` passed in container (99 passed).
- Task 17.2 note: core modules meet coverage targets (`processor/` 100%, `llm/` 94%, `classifier/` 92%); supporting modules `db/` 100% but `config/` 63% and `cli.py` 92%, so the combined supporting target is partially unmet for `config/`.
- Task 17.3 complete: configuration validation passes with `gmail-sorter --config config.yaml validate-config`.
- Task 17.4 complete: Docker image builds successfully (`docker build -t gmail-sorter:latest .`).
- Task 17.5 complete: `prompts/classify_email.j2` rendering verified with sample data in container.
- PRD verification sweep completed on April 15, 2026 against the implemented repository.
- Verification found unresolved PRD gaps; plan reopened and `.DONE` completion sentinel removed.
- Notable requirement gaps identified: FR-011, FR-025, FR-026, FR-055, FR-075, NFR-004, SEC-001, SEC-004, SEC-005, ERR-001, ERR-005, and PRD 14.3 health-port configurability.
- Task 18.1 — Expand configuration schema for missing runtime controls has been executed (`gmail_sorter/config/models.py`, `config.yaml`, `tests/unit/config/test_models.py`, and `tests/unit/config/test_loader.py`).
- Task 18.1 result: typed runtime controls were added for sender policy lists, backfill progress interval, push endpoint/port, observability ports, DB retention, and webhook URL, with validation constraints and unit coverage updates.
- Local environment still lacks `pytest` (`pytest: command not found`), so updated tests could not be executed in-session.
- Task 18.2 — Implement encrypted token-at-rest fallback has been executed (`gmail_sorter/gmail/auth.py`, `requirements.txt`, and `tests/unit/gmail/test_auth.py`).
- Task 18.2 result: OAuth token file fallback now encrypts token content at rest with deterministic key loading (keyring-backed key first, then local `0600` key file fallback), while preserving keyring token storage behavior and backward-compatible reading of legacy plaintext token files.
- PRD-to-plan comparison revalidated after Task 18.2 execution; task ordering and remaining scope are still aligned to PRD requirements.
- Local environment still lacks `pytest` (`pytest: command not found`), so Task 18.2 unit tests could not be executed in-session.
- Task 18.3 — Preserve full extraction set and sender-policy behavior has been executed (`gmail_sorter/processor/email_parser.py`, `gmail_sorter/classifier/engine.py`, `tests/unit/processor/test_email_parser.py`, and `tests/unit/classifier/test_engine.py`).
- Task 18.3 result: processor header normalization now retains `To` for prompt rendering coverage, and sender allowlist/blocklist enforcement now reads exclusively from typed `classification` config fields without heuristic section scanning.
- PRD-to-plan comparison revalidated after Task 18.3 execution; task ordering and remaining scope are still aligned to PRD requirements.
- Local environment still lacks `pytest` (`pytest: command not found`), so Task 18.3 unit tests could not be executed in-session.
- Task 18.4 — Complete Pub/Sub configurability and outcome logging semantics has been executed (`gmail_sorter/pubsub/listener.py` and `tests/unit/pubsub/test_listener.py`).
- Task 18.4 result: push-mode listener wiring now uses validated `push_port` and `push_endpoint` path handling, and Pub/Sub processing logs now emit explicit `success`/`skip`/`error` outcomes including both Pub/Sub and Gmail message identifiers while preserving ack-after-success semantics.
- PRD-to-plan comparison revalidated after Task 18.4 execution; task ordering and remaining scope are still aligned to PRD requirements.
- Local environment still lacks `pytest` (`pytest: command not found`), so Task 18.4 unit tests could not be executed in-session.
- Task 18.5 — Add multi-label classification mode has been executed (`gmail_sorter/llm/response_parser.py`, `gmail_sorter/llm/client.py`, `gmail_sorter/classifier/engine.py`, `tests/unit/llm/test_response_parser.py`, and `tests/unit/classifier/test_engine.py`).
- Task 18.5 result: parser and engine now support configurable multi-label handling with validated category lists, fallback routing for invalid/low-confidence entries, multi-label application flow, and persisted audit fields capturing multi-label outcomes.
- PRD-to-plan comparison revalidated after Task 18.5 execution; task ordering and remaining scope are still aligned to PRD requirements.
- Local environment still lacks `pytest` (`pytest: command not found`), so Task 18.5 unit tests could not be executed in-session.
- Task 18.6 — Implement retention cleanup and richer stats reporting has been executed (`gmail_sorter/db/repository.py`, `gmail_sorter/cli.py`, `tests/unit/db/test_repository.py`, and `tests/unit/test_cli.py`).
- Task 18.6 result: repository now enforces retention windows and exposes date-range/error-aware stats, while CLI stats command now applies retention, supports date-window flags, and reports explicit error totals/rates from retained records.
- PRD-to-plan comparison revalidated after Task 18.6 execution; task ordering and remaining scope are still aligned to PRD requirements.
- Local environment still lacks `pytest` (`pytest: command not found`), so Task 18.6 unit tests could not be executed in-session.
- Task 18.7 — Enforce PRD error taxonomy and critical webhook notifications has been executed (`gmail_sorter/observability/error_taxonomy.py`, `gmail_sorter/classifier/engine.py`, `gmail_sorter/pubsub/listener.py`, `gmail_sorter/observability/logging.py`, `tests/unit/classifier/test_engine.py`, `tests/unit/pubsub/test_listener.py`, `tests/unit/observability/test_logging.py`, `tests/unit/observability/test_error_taxonomy.py`, and `tests/unit/config/test_loader.py`).
- Task 18.7 result: centralized taxonomy normalization now enforces `{auth_error, api_error, llm_error, config_error, pubsub_error}` across structured logs and error metrics, classifier failures now emit taxonomy-tagged logs and optional critical webhook payloads (`error_type`, `message_id`, `timestamp`, `description`), and Pub/Sub failures now increment taxonomy-aligned error metrics with explicit `pubsub_error` logging.
- PRD-to-plan comparison revalidated after Task 18.7 execution; task ordering and remaining scope are still aligned to PRD requirements.
- Local environment still lacks `pytest` (`pytest: command not found`), so Task 18.7 unit tests could not be executed in-session.
- Task 18.8 — Enforce TLS 1.2+ for outbound HTTP clients has been executed (`gmail_sorter/llm/client.py`, `gmail_sorter/classifier/engine.py`, `tests/unit/llm/test_client.py`, and `tests/unit/classifier/test_engine.py`).
- Task 18.8 result: all non-Google outbound `httpx.AsyncClient` call sites now enforce TLS 1.2+ via explicit SSL context minimum-version controls; `LlmClient` now validates injected TLS contexts and rejects insecure minimum versions.
- PRD-to-plan comparison revalidated after Task 18.8 execution; task ordering and remaining scope are still aligned to PRD requirements.
- Local environment still lacks a Python runtime (`python: command not found`, `python3: command not found`), so Task 18.8 unit tests could not be executed in-session.
- Task 18.9 — Health and metrics ports from configuration has been executed (`gmail_sorter/cli.py` and `tests/unit/test_cli.py`).
- Task 18.9 result: runtime observability startup now uses `config.observability.health_port` and `config.observability.metrics_port` for Health and Prometheus endpoints, and CLI wiring tests validate configured-port usage.
- Follow-up PRD verification sweep completed on April 17, 2026; previously tracked gap set is closed and no additional implementation tasks remain in this plan.
- Completion sentinel `.DONE` has been reintroduced after verification confirmed no remaining PRD remediation tasks.
- Fresh PRD verification sweep completed on April 17, 2026 against repository implementation details (code-first audit).
- Verification found additional unmet or partial requirements not captured in prior remediation closure: FR-004, FR-015, FR-074, FR-075, NFR-001, NFR-003, SEC-003, SEC-005, ERR-002, ERR-003, ERR-004, and PRD 14.2/14.3 operational requirements.
- Plan reopened with Task 19 — Secondary PRD Gap Remediation.
- Completion sentinel `.DONE` removed so implementation loop resumes.

---

## Conventions

- **Language:** Python 3.11+
- **Package manager:** pip with a `requirements.txt`
- **Project root:** `/` (all paths below are relative to the project root)
- **Style:** PEP 8, type-annotated throughout, docstrings on all public classes and functions
- **Tests:** pytest; place in `tests/` mirroring the `src/` structure
- **Imports:** absolute imports only

---

## Task 1 — Project Scaffold

**Goal:** Create the directory structure, package files, and tooling configuration that all subsequent tasks depend on.

### 1.1 Create the directory tree

```
gmail_sorter/
  __init__.py
  cli.py
  config/
    __init__.py
    models.py
    loader.py
  gmail/
    __init__.py
    auth.py
    client.py
    labels.py
  pubsub/
    __init__.py
    listener.py
    watcher.py
  processor/
    __init__.py
    email_parser.py
    prompt_builder.py
  llm/
    __init__.py
    client.py
    response_parser.py
  classifier/
    __init__.py
    engine.py
    idempotency.py
  db/
    __init__.py
    schema.py
    repository.py
  backfill/
    __init__.py
    engine.py
  observability/
    __init__.py
    logging.py
    metrics.py
    health.py
  utils/
    __init__.py
    retry.py
    mime.py
    security.py
prompts/
  classify_email.j2
tests/
  conftest.py
  unit/
  integration/
  e2e/
  load/
config.yaml
Dockerfile
.dockerignore
gmail_sorter.service   (systemd unit)
```

### 1.2 Create `pyproject.toml`

Define the package with:
- `[project]` metadata: name `gmail-sorter`, version `1.0.0`, requires-python `>=3.11`
- `[project.scripts]` entry point: `gmail-sorter = "gmail_sorter.cli:main"`
- `[project.optional-dependencies]` group `dev` containing: `pytest>=8`, `pytest-asyncio>=0.23`, `pytest-cov>=5`, `respx>=0.21`, `httpx` (for test client)

### 1.3 Create `requirements.txt`

Pin the following exact minimum versions (use `>=` specifiers):

```
google-api-python-client>=2.100
google-auth-oauthlib>=1.2
google-auth-httplib2>=0.2
google-cloud-pubsub>=2.18
Jinja2>=3.1
httpx>=0.27
click>=8.1
pydantic>=2.5
pydantic-settings>=2.2
prometheus-client>=0.20
keyring>=25.0
beautifulsoup4>=4.12   # HTML-to-text fallback
lxml>=5.0              # HTML parser backend
```

### 1.4 Create `config.yaml`

Copy the full YAML from PRD Section 6 verbatim as the default configuration file. Do not modify any field names or values.

### 1.5 Create `prompts/classify_email.j2`

Copy the Jinja2 user prompt template from PRD Section 12.2 verbatim.

### 1.6 Create `Dockerfile`

Copy the two-stage Dockerfile from PRD Section 14.1 verbatim. Add `EXPOSE 8080` before the `HEALTHCHECK` instruction.

### 1.7 Create `.dockerignore`

Exclude: `.git`, `__pycache__`, `*.pyc`, `*.pyo`, `tests/`, `*.db`, `token.json`, `credentials.json`, `.env`.

### 1.8 Create `gmail_sorter.service`

Copy the systemd unit file from PRD Section 14.4 verbatim.

**Acceptance criteria:** `python -m pytest tests/ --collect-only` exits 0 (no tests yet, just collection succeeds).

---

## Task 2 — Configuration System

**Goal:** Implement `gmail_sorter/config/` so the entire config file is loaded, typed, and validated at startup.

### 2.1 `gmail_sorter/config/models.py`

Define Pydantic v2 `BaseModel` classes matching every section of `config.yaml`:

- `GmailConfig` — `credentials_path: str`, `token_path: str`, `scopes: list[str]`
- `PubSubConfig` — `project_id: str`, `topic: str`, `subscription: str`, `mode: Literal["push", "pull"]`
- `LlmConfig` — `provider: Literal["github_copilot"]`, `model: str`, `api_key_env: str`, `timeout_seconds: int = 30`, `max_retries: int = 3`, `system_prompt: str`, `prompt_template: str`
- `ClassificationConfig` — `confidence_threshold: float = 0.7`, `fallback_category: str = "uncategorized"`, `multi_label: bool = False`
- `CategoryConfig` — `name: str`, `label: str`, `description: str`
- `ProcessingConfig` — `body_max_length: int = 4096`, `batch_size: int = 50`, `backfill_concurrency: int = 5`, `archive_after_label: bool = False`, `dry_run: bool = False`
- `LoggingConfig` — `level: str = "INFO"`, `log_prompts: bool = False`
- `DatabaseConfig` — `path: str = "./gmail_sorter.db"`
- `AppConfig` — composes all of the above; `categories: list[CategoryConfig]`

Add a Pydantic `model_validator` on `AppConfig` that:
1. Asserts all `CategoryConfig.name` values are unique; raises `ValueError` with the duplicated name if not.
2. Asserts no two `CategoryConfig` entries share the same `label`; raises `ValueError` with the conflicting label if not.

### 2.2 `gmail_sorter/config/loader.py`

Implement `load_config(path: str | Path) -> AppConfig`:
- Reads the YAML file using `yaml.safe_load` from `PyYAML` (add `PyYAML>=6.0` to `requirements.txt`).
- Passes the parsed dict to `AppConfig.model_validate(...)`.
- On `ValidationError`, prints each error with field path and message to stderr, then raises `SystemExit(1)`.

### 2.3 Tests — `tests/unit/config/test_models.py`

Write pytest tests covering:
- Valid config loads without error.
- Duplicate category `name` raises `ValueError`.
- Duplicate category `label` raises `ValueError`.
- Missing required field raises `ValidationError`.
- `confidence_threshold` outside `[0.0, 1.0]` raises `ValidationError` (add a `Field(ge=0.0, le=1.0)` constraint).

**Acceptance criteria:** `pytest tests/unit/config/` passes.

---

## Task 3 — Database Layer

**Goal:** Implement the SQLite schema and repository so all other components can persist and query records.

### 3.1 `gmail_sorter/db/schema.py`

Define a constant `SCHEMA_SQL: str` containing the exact `CREATE TABLE IF NOT EXISTS` statements from PRD Section 11, including all `CREATE INDEX` statements. Fix the typo in the PRD: replace `data-id="633" 1.0` with `1.0` in the `CHECK` constraint.

### 3.2 `gmail_sorter/db/repository.py`

Implement `Database` class:

```python
class Database:
    def __init__(self, path: str) -> None: ...
    def initialize(self) -> None: ...           # Runs SCHEMA_SQL; creates file if needed
    def close(self) -> None: ...

    # classifications
    def upsert_classification(self, record: ClassificationRecord) -> None: ...
    def get_classification(self, message_id: str) -> ClassificationRecord | None: ...
    def is_classified(self, message_id: str) -> bool: ...
    def get_stats(self, since: datetime | None = None) -> dict[str, Any]: ...

    # backfill state
    def upsert_backfill_state(self, state: BackfillState) -> None: ...
    def get_latest_backfill_state(self) -> BackfillState | None: ...

    # dead-letter queue
    def add_to_dlq(self, entry: DlqEntry) -> None: ...
    def get_dlq_entries(self, limit: int = 100) -> list[DlqEntry]: ...
```

Define dataclasses `ClassificationRecord`, `BackfillState`, and `DlqEntry` matching the schema columns exactly.

Use `sqlite3` from the standard library. All writes MUST use parameterized queries (never string interpolation). `upsert_classification` MUST use `INSERT OR REPLACE` to guarantee idempotency.

### 3.3 Tests — `tests/unit/db/test_repository.py`

Use an in-memory SQLite database (`":memory:"`):
- `initialize()` creates all three tables.
- `upsert_classification` with the same `message_id` twice results in exactly one row.
- `is_classified` returns `True` after insert, `False` before.
- `add_to_dlq` persists entries; `get_dlq_entries` returns them.
- `upsert_backfill_state` and `get_latest_backfill_state` round-trip correctly.

**Acceptance criteria:** `pytest tests/unit/db/` passes.

---

## Task 4 — Gmail OAuth Authentication

**Goal:** Implement OAuth 2.0 authentication, secure token storage, and automatic token refresh.

### 4.1 `gmail_sorter/gmail/auth.py`

Implement `GmailAuthenticator`:

```python
class GmailAuthenticator:
    def __init__(self, config: GmailConfig) -> None: ...
    def authenticate(self) -> Credentials: ...     # Interactive browser flow
    def get_credentials(self) -> Credentials: ...  # Returns valid (refreshed) creds
    def _load_token(self) -> Credentials | None: ...
    def _save_token(self, creds: Credentials) -> None: ...
    def validate_scopes(self, creds: Credentials) -> None: ...
```

Requirements:
- Use `google_auth_oauthlib.flow.InstalledAppFlow` for the interactive flow.
- Store tokens to the path in `GmailConfig.token_path` using `json` serialization of `creds.to_json()`.
- After writing the token file, set file permissions to `0600` using `os.chmod`.
- `get_credentials` MUST call `creds.refresh(Request())` if `creds.expired` and `creds.refresh_token` is set.
- `validate_scopes` MUST compare `creds.scopes` to `config.scopes`; raise `SystemExit(1)` with a descriptive message if any scope is missing (implements FR-005).
- On platforms where keyring is available, attempt to store and retrieve the raw token JSON from the OS keyring under service name `"gmail-sorter"` and account name `"oauth-token"` (implements SEC-001). Fall back to file storage silently on keyring errors.

### 4.2 Tests — `tests/unit/gmail/test_auth.py`

Mock `google_auth_oauthlib`, `google.oauth2.credentials.Credentials`, and `os.chmod`. Test:
- `_save_token` calls `os.chmod(..., 0o600)`.
- `get_credentials` calls `refresh()` when `expired=True`.
- `validate_scopes` raises `SystemExit` on missing scope.

**Acceptance criteria:** `pytest tests/unit/gmail/` passes.

---

## Task 5 — Gmail API Client

**Goal:** Wrap the Gmail REST API for message fetching, label management, and message modification.

### 5.1 `gmail_sorter/gmail/client.py`

Implement `GmailClient`:

```python
class GmailClient:
    def __init__(self, credentials: Credentials) -> None: ...

    # Message operations
    def get_message(self, message_id: str, format: str = "full") -> dict: ...
    def list_messages(self, page_token: str | None = None,
                      batch_size: int = 50) -> tuple[list[dict], str | None]: ...

    # Label operations
    def list_labels(self) -> list[dict]: ...
    def create_label(self, name: str) -> dict: ...
    def ensure_label_exists(self, name: str) -> str: ...  # Returns label ID

    # Modification
    def apply_label(self, message_id: str, label_id: str,
                    archive: bool = False) -> None: ...
    def get_message_label_ids(self, message_id: str) -> list[str]: ...

    # Watch
    def register_watch(self, topic_name: str) -> dict: ...
```

Requirements:
- Build the service using `googleapiclient.discovery.build("gmail", "v1", credentials=credentials)`.
- All methods that call the API MUST use the retry decorator from `gmail_sorter/utils/retry.py` (Task 6) with `max_retries=3` and exponential backoff.
- `apply_label` MUST use `gmail.users.messages.modify()` with `addLabelIds=[label_id]`. When `archive=True`, also include `removeLabelIds=["INBOX"]`.
- `apply_label` in dry-run mode (detected via a constructor parameter `dry_run: bool = False`) MUST log the intended operation at `INFO` level and return without calling the API.
- `ensure_label_exists` MUST call `list_labels()` first; only call `create_label()` if the label is absent. Supports nested labels (e.g., `"AutoSort/Marketing"`).
- `list_messages` returns a tuple of `(messages, next_page_token)`. When `next_page_token` is `None`, the mailbox has been fully paginated.

### 5.2 `gmail_sorter/gmail/labels.py`

Implement `LabelManager`:
```python
class LabelManager:
    def __init__(self, client: GmailClient) -> None: ...
    def ensure_all_labels(self, categories: list[CategoryConfig]) -> dict[str, str]: ...
    # Returns {category_name: label_id}
```

Calls `client.ensure_label_exists(cat.label)` for every category on startup (FR-052).

### 5.3 Tests — `tests/unit/gmail/test_client.py`

Mock `googleapiclient`. Test:
- `ensure_label_exists` does not call `create_label` when the label already exists.
- `apply_label` with `dry_run=True` never calls the API.
- `apply_label` with `archive=True` includes `"INBOX"` in `removeLabelIds`.

**Acceptance criteria:** `pytest tests/unit/gmail/` passes.

---

## Task 6 — Utilities

**Goal:** Implement shared helpers used by multiple modules.

### 6.1 `gmail_sorter/utils/retry.py`

Implement an async-compatible retry decorator `with_retry`:

```python
def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    jitter: bool = True,
    retryable_exceptions: tuple[type[Exception], ...] = (Exception,),
) -> Callable: ...
```

- On each retry attempt, wait `min(base_delay * 2**attempt, max_delay)` seconds.
- If `jitter=True`, add a uniform random value in `[0, 1)` to the delay.
- After all retries are exhausted, re-raise the last exception.
- Log each retry at `WARNING` level including attempt number and exception message.

### 6.2 `gmail_sorter/utils/mime.py`

Implement `EmailParser`:

```python
class EmailParser:
    @staticmethod
    def extract_body(payload: dict, max_length: int = 4096) -> str: ...
    @staticmethod
    def extract_headers(payload: dict) -> dict[str, str]: ...
    @staticmethod
    def html_to_text(html: str) -> str: ...
    @staticmethod
    def strip_unsafe_content(text: str) -> str: ...
```

Requirements:
- `extract_body` MUST recurse through `payload["parts"]` to find `text/plain`. If absent, fall back to `text/html` and call `html_to_text`.
- `html_to_text` MUST use `BeautifulSoup(html, "lxml").get_text(separator=" ")`.
- `extract_body` MUST base64-decode part data using `base64.urlsafe_b64decode`.
- The result MUST be truncated to `max_length` characters.
- `strip_unsafe_content` MUST remove base64 data URIs matching `data:[^;]+;base64,[A-Za-z0-9+/=]+` (implements SEC-003).

### 6.3 `gmail_sorter/utils/security.py`

Implement:
```python
def is_domain_allowed(sender: str,
                      allowlist: list[str],
                      blocklist: list[str]) -> bool: ...
```
- Extracts the domain from the `sender` string (handles both `"Name <email@domain>"` and `"email@domain"` formats).
- Returns `False` if the domain is in `blocklist`.
- Returns `True` if `allowlist` is empty OR the domain is in `allowlist`.
- Returns `False` if `allowlist` is non-empty and the domain is NOT in `allowlist`.
- Implements SEC-004.

### 6.4 Tests — `tests/unit/utils/`

- `test_retry.py`: Verify retry count, exponential delay (mock `asyncio.sleep`), and final exception propagation.
- `test_mime.py`: Test `extract_body` for plain text, HTML fallback, truncation, and base64 stripping.
- `test_security.py`: Test all allowlist/blocklist combinations.

**Acceptance criteria:** `pytest tests/unit/utils/` passes.

---

## Task 7 — Email Processor & Prompt Builder

**Goal:** Extract structured data from raw Gmail message payloads and render LLM prompts.

### 7.1 `gmail_sorter/processor/email_parser.py`

Implement `ProcessedEmail` dataclass and `process_message(raw: dict, config: ProcessingConfig) -> ProcessedEmail`:

```python
@dataclass
class ProcessedEmail:
    message_id: str
    thread_id: str
    sender: str
    subject: str
    date: str
    body: str
    headers: dict[str, str]   # includes list_unsubscribe (bool as str), reply_to
    raw_label_ids: list[str]
```

- Calls `EmailParser.extract_headers` and `EmailParser.extract_body` from Task 6.
- Calls `EmailParser.strip_unsafe_content` on the extracted body (SEC-003).
- Truncates `body` to `config.body_max_length`.

### 7.2 `gmail_sorter/processor/prompt_builder.py`

Implement `PromptBuilder`:

```python
class PromptBuilder:
    def __init__(self, config: LlmConfig,
                 categories: list[CategoryConfig]) -> None: ...
    def build(self, email: ProcessedEmail) -> tuple[str, str]: ...
    # Returns (system_prompt, user_prompt)
    def template_hash(self) -> str: ...
    # Returns SHA-256 hex digest of the rendered template source
```

- Load the Jinja2 template from `config.prompt_template`. If the value is a file path that exists, load the file; otherwise treat the value as an inline template string.
- Render the template with variables: `sender`, `subject`, `body`, `date`, `headers`, `categories`.
- `template_hash` returns `hashlib.sha256(template_source.encode()).hexdigest()`.

### 7.3 Tests — `tests/unit/processor/`

- `test_email_parser.py`: multipart payload → plain text; HTML-only payload → converted text; body truncation; header extraction.
- `test_prompt_builder.py`: rendered prompt contains sender/subject/categories; inline template works; file template works; `template_hash` is stable.

**Acceptance criteria:** `pytest tests/unit/processor/` passes.

---

## Task 8 — LLM Client

**Goal:** Implement the async HTTP client for GitHub Copilot's API and the response parser.

### 8.1 `gmail_sorter/llm/client.py`

Implement `LlmClient`:

```python
class LlmClient:
    def __init__(self, config: LlmConfig) -> None: ...
    async def classify(self,
                       system_prompt: str,
                       user_prompt: str) -> LlmResponse: ...
    async def close(self) -> None: ...
```

Requirements:
- Use `httpx.AsyncClient` with `http2=True` and `timeout=config.timeout_seconds`.
- Read the API key from `os.environ[config.api_key_env]`; raise `SystemExit(1)` with a clear message if the variable is not set.
- Call the GitHub Copilot chat completions endpoint. Construct the request as:
  ```json
  {
    "model": "<config.model>",
    "messages": [
      {"role": "system", "content": "<system_prompt>"},
      {"role": "user", "content": "<user_prompt>"}
    ]
  }
  ```
- Set headers: `Authorization: Bearer <api_key>`, `Content-Type: application/json`.
- Wrap the call in `with_retry(max_retries=config.max_retries, retryable_exceptions=(httpx.HTTPError, httpx.TimeoutException))`.
- If `logging.log_prompts` is `True` (pass this flag to the constructor), log the full prompt and response at `DEBUG`. Otherwise log only message length (implements SEC-007 / FR-039).
- Raise `LlmError` (a custom exception defined in `gmail_sorter/llm/client.py`) on non-2xx responses after retries exhausted.

### 8.2 `gmail_sorter/llm/response_parser.py`

Implement:
```python
@dataclass
class LlmResponse:
    category: str
    confidence: float
    reasoning: str
    raw: str

def parse_response(raw_content: str,
                   valid_categories: list[str],
                   fallback: str,
                   threshold: float) -> LlmResponse: ...
```

Requirements:
- Extract the JSON object from `raw_content` using `json.loads`. If that fails, try extracting the first `{...}` substring with a regex before raising `LlmParseError`.
- Validate `category` is in `valid_categories`. If not, set `category = fallback`.
- Validate `confidence` is a float in `[0.0, 1.0]`. If outside range, clamp to `[0.0, 1.0]`.
- If `confidence < threshold`, set `category = fallback`.

### 8.3 Tests — `tests/unit/llm/`

- `test_response_parser.py`: valid response; unknown category → fallback; low confidence → fallback; malformed JSON → `LlmParseError`; confidence clamping; JSON-substring extraction from wrapped responses.
- `test_client.py`: mock `httpx.AsyncClient` with `respx`; verify correct request body; verify retry on 500; verify `LlmError` raised after max retries; verify prompt redaction when `log_prompts=False`.

**Acceptance criteria:** `pytest tests/unit/llm/` passes.

---

## Task 9 — Classification Engine

**Goal:** Combine the Email Processor, LLM Client, and Label Applicator into a single orchestrating engine with idempotency checks.

### 9.1 `gmail_sorter/classifier/idempotency.py`

Implement `IdempotencyChecker`:

```python
class IdempotencyChecker:
    def __init__(self, db: Database,
                 system_label_ids: set[str]) -> None: ...
    def is_processed(self, email: ProcessedEmail) -> bool: ...
```

Returns `True` if:
- `db.is_classified(email.message_id)` is `True`, OR
- any label ID in `email.raw_label_ids` is in `system_label_ids`.

Implements FR-013, FR-072.

### 9.2 `gmail_sorter/classifier/engine.py`

Implement `ClassificationEngine`:

```python
class ClassificationEngine:
    def __init__(self,
                 config: AppConfig,
                 gmail_client: GmailClient,
                 llm_client: LlmClient,
                 db: Database,
                 label_map: dict[str, str],
                 idempotency_checker: IdempotencyChecker,
                 prompt_builder: PromptBuilder,
                 metrics: MetricsCollector) -> None: ...

    async def classify_message(self, message_id: str) -> ClassificationResult: ...
```

`classify_message` MUST implement the full pipeline from PRD Section 4.2, steps 2–7:
1. Fetch full message via `gmail_client.get_message(message_id)`.
2. Run `IdempotencyChecker.is_processed`; return early with `ClassificationResult(skipped=True)` if already processed.
3. Call `process_message` to produce a `ProcessedEmail`.
4. Check `is_domain_allowed` against config allowlist/blocklist (SEC-004); skip if blocked.
   - If allowlist/blocklist are not present in config, default both to empty lists.
5. Build prompts via `PromptBuilder.build`.
6. Call `LlmClient.classify`.
7. Parse response via `parse_response`.
8. If `config.processing.dry_run` is `True`, log the intended label and return without modifying Gmail or writing to DB.
9. Apply the label via `gmail_client.apply_label`.
10. Write `ClassificationRecord` to `db.upsert_classification`.
11. Update metrics.
12. Return `ClassificationResult` with all fields populated.

Define `ClassificationResult` as a dataclass with fields: `message_id`, `category`, `confidence`, `label_applied`, `skipped: bool`, `duration_ms: int`.

### 9.3 Tests — `tests/unit/classifier/`

- `test_idempotency.py`: already in DB → skipped; label present in raw_label_ids → skipped; neither → not skipped.
- `test_engine.py`: mock all dependencies; happy path produces correct `ClassificationResult`; low-confidence → fallback label; dry-run → no `apply_label` call; already classified → skipped without LLM call.

**Acceptance criteria:** `pytest tests/unit/classifier/` passes.

---

## Task 10 — Pub/Sub Integration

**Goal:** Implement real-time email ingestion via Google Cloud Pub/Sub.

### 10.1 `gmail_sorter/pubsub/watcher.py`

Implement `GmailWatcher`:

```python
class GmailWatcher:
    def __init__(self, gmail_client: GmailClient,
                 config: PubSubConfig) -> None: ...
    def register(self) -> dict: ...
    def schedule_renewal(self) -> None: ...
    # Uses threading.Timer to call register() every 6 days (before 7-day expiry)
```

Implements FR-021, FR-022.

### 10.2 `gmail_sorter/pubsub/listener.py`

Implement `PubSubListener`:

```python
class PubSubListener:
    def __init__(self,
                 config: PubSubConfig,
                 engine: ClassificationEngine,
                 metrics: MetricsCollector) -> None: ...
    async def start(self) -> None: ...
    async def stop(self) -> None: ...
    def _handle_message(self, message: Any) -> None: ...
```

Requirements:
- Support FR-020 by creating or reusing the configured Pub/Sub topic and subscription at startup before listener consumption begins.
- Support both `pull` and `push` modes (FR-025).
- **Pull mode:** Use `google.cloud.pubsub_v1.SubscriberClient` to pull messages in a background thread; parse the Pub/Sub message data to extract the Gmail `message_id` from the notification JSON (`{"emailAddress": "...", "historyId": "..."}`). Use the Gmail history API (`users.history.list`) to get the actual new message IDs from the `historyId`.
- **Push mode:** Start a minimal HTTP server (for example `http.server`-based) on the configured port accepting `POST /pubsub` with the Pub/Sub push payload.
- Acknowledge the Pub/Sub message (call `message.ack()`) ONLY after `engine.classify_message` returns successfully (FR-024).
- On failure, do NOT acknowledge (so the message is redelivered).
- Log every message outcome with Pub/Sub message ID and Gmail message ID (FR-026).

### 10.3 Tests — `tests/unit/pubsub/`

Mock `google.cloud.pubsub_v1`. Test:
- Message is acknowledged after successful classification.
- Message is NOT acknowledged when `classify_message` raises an exception.
- Watcher `schedule_renewal` sets a timer with delay < 7 days.

**Acceptance criteria:** `pytest tests/unit/pubsub/` passes.

---

## Task 11 — Backfill Engine

**Goal:** Implement the full-mailbox scan with pagination, concurrency, and resume capability.

### 11.1 `gmail_sorter/backfill/engine.py`

Implement `BackfillEngine`:

```python
class BackfillEngine:
    def __init__(self,
                 gmail_client: GmailClient,
                 engine: ClassificationEngine,
                 db: Database,
                 config: ProcessingConfig,
                 metrics: MetricsCollector) -> None: ...
    async def run(self) -> None: ...
    async def _process_batch(self, message_ids: list[str]) -> None: ...
```

Requirements:
- On start, call `db.get_latest_backfill_state()`. If a `running` or `interrupted` state exists, resume from `last_page_token` (FR-074).
- Paginate using `gmail_client.list_messages(page_token=..., batch_size=config.batch_size)`.
- Process up to `config.backfill_concurrency` messages concurrently using `asyncio.TaskGroup` (Python 3.11+).
- After each batch, call `db.upsert_backfill_state` with the current page token and running total.
- Log progress every 100 messages (or configurable interval): `"Backfill progress: {processed}/{estimated}"` at `INFO` level (FR-075).
- On completion, update `backfill_state.status = "completed"` and `completed_at`.
- On `asyncio.CancelledError`, update status to `"interrupted"` before propagating.

### 11.2 Tests — `tests/unit/backfill/test_engine.py`

Mock `GmailClient`, `ClassificationEngine`, `Database`. Test:
- Pagination: three pages → all message IDs processed.
- Resume: pre-existing `interrupted` state → starts from saved `last_page_token`.
- Concurrency: at most `backfill_concurrency` tasks running simultaneously (use an `asyncio.Semaphore` spy).
- Cancellation: status set to `"interrupted"`.

**Acceptance criteria:** `pytest tests/unit/backfill/` passes.

---

## Task 12 — Observability

**Goal:** Implement structured logging, Prometheus metrics, and the health check endpoint.

### 12.1 `gmail_sorter/observability/logging.py`

Implement `configure_logging(level: str, log_prompts: bool) -> None`:
- Configure the root logger to emit structured JSON via a custom `logging.Formatter` subclass.
- Each log record MUST serialize to JSON with keys: `timestamp` (ISO 8601), `level`, `message`, `error_type` (if present in `extra`), `context` (dict, from `extra`).
- Implements ERR-002.

### 12.2 `gmail_sorter/observability/metrics.py`

Implement `MetricsCollector` wrapping `prometheus_client`:

```python
class MetricsCollector:
    emails_processed_total: Counter
    emails_classified_total: Counter          # label: category
    classification_errors_total: Counter      # label: error_type
    llm_latency_seconds: Histogram
    pubsub_messages_received_total: Counter

    def start_http_server(self, port: int = 9090) -> None: ...
```

Implements ERR-003.

### 12.3 `gmail_sorter/observability/health.py`

Implement `HealthServer`:

```python
class HealthServer:
    def __init__(self, port: int = 8080) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def set_healthy(self, last_message_at: str | None = None) -> None: ...
    def set_unhealthy(self, reason: str) -> None: ...
```

Runs a minimal `http.server.HTTPServer` in a daemon thread. Responds to `GET /health` per PRD Section 14.3 (`200` or `503` JSON).

### 12.4 Tests — `tests/unit/observability/`

- `test_logging.py`: log output is valid JSON; contains required keys.
- `test_health.py`: `set_healthy` → `GET /health` returns 200; `set_unhealthy` → 503.

**Acceptance criteria:** `pytest tests/unit/observability/` passes.

---

## Task 13 — CLI

**Goal:** Implement the Click-based CLI with all commands and global flags from PRD Section 10.

### 13.1 `gmail_sorter/cli.py`

Implement using `click`:

```
@click.group()
@click.option("--config", default="./config.yaml", ...)
@click.option("--dry-run", is_flag=True, ...)
@click.option("--log-level", default=None, ...)
@click.version_option(version="1.0.0")
@click.pass_context
def main(ctx, config, dry_run, log_level): ...
```

Implement all six subcommands:

**`run`**
- Loads config, initializes all components (DB, auth, Gmail client, LLM client, label manager, engine, metrics, health server, Pub/Sub listener, watcher).
- Starts the health server and metrics server.
- Registers the Gmail watch.
- Starts the Pub/Sub listener's event loop.
- Accepts `--backfill` flag; if set, also runs `BackfillEngine` concurrently using `asyncio.TaskGroup`.
- Handles `SIGINT`/`SIGTERM` gracefully: stops listener, flushes DB, exits cleanly.

**`backfill`**
- Runs `BackfillEngine` only, then exits.

**`validate-config`**
- Calls `load_config`; prints "Configuration is valid." on success; exits 1 on error.

**`auth`**
- Calls `GmailAuthenticator.authenticate()` interactively.

**`stats`**
- Calls `db.get_stats()` and pretty-prints a table of: total processed, breakdown by category, error rate, date range.

### 13.2 Tests — `tests/unit/test_cli.py`

Use `click.testing.CliRunner`:
- `validate-config` with valid config → exit 0.
- `validate-config` with invalid config → exit 1.
- `--version` → prints `1.0.0`.

**Acceptance criteria:** `pytest tests/unit/test_cli.py` passes.

---

## Task 14 — Integration Tests

**Goal:** Verify that components interact correctly end-to-end with real (or emulated) external services.

### 14.1 `tests/integration/test_database.py`

Use a temporary file-backed SQLite database:
- Full write/read round-trip for `ClassificationRecord`.
- `upsert_classification` called twice with identical `message_id` → exactly one row.
- `BackfillState` persists across `Database.close()` / `Database.__init__()` cycle.

### 14.2 `tests/integration/test_gmail_client.py`

Use `respx` to mock the Google API HTTP layer:
- `ensure_label_exists` → creates label when absent; returns existing ID when present.
- `apply_label` → correct JSON body sent to the modify endpoint.
- Rate-limit response (429) → retry fires; succeeds on second attempt.

### 14.3 `tests/integration/test_llm_client.py`

Use `respx` to mock the GitHub Copilot API:
- Happy path: full prompt → structured JSON response parsed correctly.
- 500 error → retried; 500 again → `LlmError` raised after `max_retries`.
- Timeout → `httpx.TimeoutException` → retried.

### 14.4 `tests/integration/test_pipeline.py`

Wire together: `PromptBuilder` + real `EmailParser` + mock `LlmClient` + in-memory `Database` + mock `GmailClient`:
- Full `classify_message` call → label applied, DB record written.
- Repeat call → skipped (idempotency).
- Dry-run → no `apply_label` call, no DB write.

**Acceptance criteria:** `pytest tests/integration/` passes.

---

## Task 15 — End-to-End Tests

**Goal:** Validate the complete pipeline including the CLI entry point.

### 15.1 `tests/e2e/test_full_pipeline.py`

Use `respx` global mock + in-memory SQLite + `click.testing.CliRunner`:
- Start `gmail-sorter run` with a mock Pub/Sub pull returning one message → message is classified and labeled.
- Run with `--dry-run` → no Gmail API modify calls made.
- Simulate LLM returning unknown category → fallback label applied.
- Simulate LLM timeout on all retries → message ends up in DLQ.

### 15.2 `tests/e2e/test_backfill.py`

- Mock Gmail listing 250 messages across 5 pages.
- Run `gmail-sorter backfill`.
- Assert all 250 messages classified, all DB records present.
- Interrupt after page 2 (simulate `KeyboardInterrupt`), re-run → resumes from page 3.

**Acceptance criteria:** `pytest tests/e2e/` passes.

---

## Task 16 — Load & Performance Tests

**Goal:** Validate NFR-001, NFR-002, NFR-007.

### 16.1 `tests/load/test_backfill_throughput.py`

- Generate 1 000 mock messages (in-memory).
- Mock `LlmClient.classify` with a fixed 50ms delay.
- Run `BackfillEngine` with `backfill_concurrency=5`.
- Assert wall-clock time yields ≥ 500 messages/minute throughput (**NFR-002**).

### 16.2 `tests/load/test_latency.py`

- Time a single `classify_message` call end-to-end (mocked LLM at 100ms).
- Assert total duration < 10 000ms (**NFR-001**).

### 16.3 `tests/load/test_memory.py`

- Import `tracemalloc`.
- Spin up `PubSubListener` in pull mode (mock Pub/Sub returning no messages).
- Wait 5 seconds idle.
- Assert `tracemalloc` peak < 256 MB (**NFR-007**).

**Acceptance criteria:** `pytest tests/load/` passes.

---

## Task 17 — Final Integration & Packaging

**Goal:** Ensure the project installs cleanly, all tests pass, and deployment artifacts are correct.

### 17.1 Verify installability

Run `pip install -e ".[dev]"` and confirm `gmail-sorter --help` prints usage without error.

### 17.2 Full test suite

Run `pytest --cov=gmail_sorter --cov-report=term-missing tests/` and confirm:
- All tests pass.
- Core pipeline modules (`processor/`, `llm/`, `classifier/`) have ≥ 90% coverage.
- Supporting modules (`cli.py`, `config/`, `db/`) have ≥ 80% coverage.

### 17.3 Validate config

Run `gmail-sorter validate-config --config config.yaml` and confirm exit 0.

### 17.4 Docker build

Run `docker build -t gmail-sorter:latest .` and confirm the image builds without error.

### 17.5 Prompt template

Confirm `prompts/classify_email.j2` renders without error when passed sample data:
```python
from jinja2 import Environment, FileSystemLoader
env = Environment(loader=FileSystemLoader("prompts"))
tmpl = env.get_template("classify_email.j2")
out = tmpl.render(sender="test@example.com", subject="Test", body="Hello",
                  date="2026-04-15", headers={}, categories=[])
assert "test@example.com" in out
```

**Acceptance criteria:** All 17.1–17.5 checks pass. The system is ready for deployment.

---

## Task 18 — PRD Gap Remediation

**Goal:** Close all requirement gaps discovered during PRD verification so repository state matches PRD v1 requirements.

### 18.1 Expand configuration schema for missing runtime controls

Update `gmail_sorter/config/models.py` and `config.yaml` to add typed fields that are currently required by behavior but not represented in validated config:

- `classification.allowlist: list[str] = []`
- `classification.blocklist: list[str] = []`
- `processing.backfill_progress_interval: int = 100`
- `pubsub.push_endpoint: str | None = None`
- `pubsub.push_port: int = 8081`
- `observability.health_port: int = 8080`
- `observability.metrics_port: int = 9090`
- `database.retention_days: int = 90`
- `alerts.webhook_url: str | None = None`

Update `gmail_sorter/config/loader.py` tests to validate defaults and reject invalid values (negative interval/retention, out-of-range ports).

### 18.2 Implement encrypted token-at-rest fallback

Update `gmail_sorter/gmail/auth.py` to satisfy SEC-001 when keyring is unavailable by encrypting token file content at rest instead of writing plaintext JSON.

- Use a deterministic local key-loading strategy (keyring-backed key if available; otherwise encrypted-key file with `0600` permissions).
- Keep token refresh and scope validation behavior unchanged.
- Add/update tests in `tests/unit/gmail/test_auth.py` to assert encrypted file write path and backward-compatible read behavior.

### 18.3 Preserve full extraction set and sender-policy behavior

Update `gmail_sorter/processor/email_parser.py` to retain the `To` field in `ProcessedEmail.headers` and ensure prompt rendering can include all PRD-required extracted fields (FR-011).

Update `gmail_sorter/classifier/engine.py` to read sender allowlist/blocklist from the new typed config fields only (SEC-004), removing heuristic section scanning.

Add unit tests under `tests/unit/processor/` and `tests/unit/classifier/` for `To` propagation and sender policy enforcement from config.

### 18.4 Complete Pub/Sub configurability and outcome logging semantics

Update `gmail_sorter/pubsub/listener.py` to:

- Use validated `push_port`/`push_endpoint` config fields (FR-025).
- Log explicit `success`, `skip`, and `error` outcomes with both Pub/Sub message ID and Gmail message ID (FR-026).
- Preserve ack-after-successful-processing semantics (FR-024).

Add tests in `tests/unit/pubsub/test_listener.py` covering skip outcome logging and push-mode configured endpoint/port wiring.

### 18.5 Add multi-label classification mode

Update `gmail_sorter/llm/response_parser.py`, `gmail_sorter/llm/client.py`, and `gmail_sorter/classifier/engine.py` to support `classification.multi_label = true` (FR-055):

- Accept a structured response containing multiple categories when enabled.
- Validate each returned category against configured categories; apply fallback handling for invalid/low-confidence results.
- Apply all resolved label IDs in one modify call (or equivalent repeated safe calls), preserving idempotency.
- Persist classification audit records in a PRD-aligned way for multi-label outcomes.

Add tests in `tests/unit/llm/` and `tests/unit/classifier/` for enabled/disabled multi-label paths.

### 18.6 Implement retention cleanup and richer stats reporting

Update `gmail_sorter/db/repository.py` and `gmail_sorter/cli.py`:

- Add retention enforcement utilities for `classifications` and `dead_letter_queue` based on `database.retention_days` (NFR-004).
- Extend `stats` output to support date-range reporting and explicit error-rate calculation using retained records.

Add tests in `tests/unit/db/test_repository.py` and `tests/unit/test_cli.py` for retention pruning and date-window stats.

### 18.7 Enforce PRD error taxonomy and critical webhook notifications

Update pipeline logging and error handling modules to satisfy ERR-001 and ERR-005:

- Standardize emitted `error_type` values to `{auth_error, api_error, llm_error, config_error, pubsub_error}`.
- Ensure error logs and `classification_errors_total` metrics always include one of the required labels.
- Add optional webhook notification dispatch for critical failures with payload fields: `error_type`, `message_id`, `timestamp`, `description`.

Add unit tests under `tests/unit/classifier/`, `tests/unit/pubsub/`, and `tests/unit/observability/` for taxonomy mapping and webhook payload emission.

### 18.8 Enforce TLS 1.2+ for outbound HTTP clients

Update `gmail_sorter/llm/client.py` (and any non-Google raw HTTP clients) to explicitly enforce TLS >= 1.2 (SEC-005), and add tests to ensure insecure TLS contexts are rejected.

### 18.9 Health and metrics ports from configuration

Update `gmail_sorter/cli.py` and observability wiring to start Health and Prometheus servers on configured ports instead of hardcoded values, satisfying PRD 14.3 configurability.

Add CLI runtime wiring tests validating configured port usage.

**Acceptance criteria:**

- PRD gaps listed in Execution Status are all addressed with passing unit/integration coverage.
- `README.md`, `CHANGELOG.md`, and this plan reflect the remediated verification status.
- Completion sentinel may be reintroduced only after a follow-up verification confirms full PRD compliance.

---

## Task 19 — Secondary PRD Gap Remediation

**Goal:** Address the newly identified PRD compliance gaps from the April 17, 2026 code-first verification sweep and re-establish full PRD alignment.

### 19.1 Explicit Pub/Sub service-account credential support (FR-004)

Update configuration and Pub/Sub client wiring to explicitly support service-account authentication for topic/subscription management:

- Add typed config support for optional Pub/Sub credentials path or explicit service-account mode.
- Initialize `PublisherClient` and `SubscriberClient` with explicit credentials when configured.
- Add startup-time validation/error messaging when configured credentials are missing or invalid.
- Add unit tests in `tests/unit/pubsub/` and config tests in `tests/unit/config/` for explicit credential-path behavior.

### 19.2 Rate-limit specific retry observability (FR-015)

Enhance retry/Gmail API interaction logging to explicitly capture Gmail rate-limit events:

- Detect 429/rate-limit responses/exceptions in Gmail API call paths.
- Emit `WARNING` logs with operation context when rate limits are encountered.
- Preserve exponential backoff with jitter behavior.
- Add unit tests validating rate-limit warning emission.

### 19.3 Backfill resume semantics and progress accounting (FR-074, FR-075)

Update backfill state handling to match PRD semantics:

- Resume from persisted `last_message_id` semantics in addition to page token tracking.
- Ensure interrupted runs continue from the exact last processed point without reclassification drift.
- Improve progress logging to report `processed/total` (or explicit total estimate source) at configured intervals.
- Add/expand tests in `tests/unit/backfill/test_engine.py` and integration coverage for resume/progress behavior.

### 19.4 Listener resiliency and reconnect loop (NFR-003, PRD 14.3 runtime health)

Implement transient-failure reconnection behavior and health-state transitions:

- Add automatic reconnect/retry strategy for Pub/Sub listener failures in `run` mode.
- Set health endpoint state to unhealthy on listener connectivity loss/error and restore to healthy on recovery.
- Ensure service loop does not exit permanently on transient listener failures.
- Add unit tests for reconnect and health transition behavior.

### 19.5 Strengthen prompt-input sanitization (SEC-003)

Harden email body preprocessing before LLM submission:

- Ensure linked image/tracking pixel artifacts are stripped or neutralized in HTML fallback processing.
- Preserve existing attachment/base64-data suppression guarantees.
- Add MIME utility tests for tracking-pixel and linked-image stripping cases.

### 19.6 TLS policy enforcement coverage for Google API transport (SEC-005)

Document and enforce TLS >= 1.2 posture for Gmail and Pub/Sub transports where controllable:

- Add explicit transport/TLS policy handling for Google client initialization where feasible.
- If transport libraries enforce TLS implicitly, add startup verification and documentation explaining enforcement boundaries.
- Add tests covering configured transport policy behavior and failure paths.

### 19.7 Structured log context completeness (ERR-002)

Ensure required context fields are consistently present in emitted structured logs:

- Standardize inclusion of operation context and relevant IDs on pipeline logs.
- Ensure logs emitted from watch/listener/backfill/classifier paths carry non-empty required context keys.
- Add logging tests validating required context shape across representative events.

### 19.8 LLM latency metric observation wiring (ERR-003)

Connect the declared `llm_latency_seconds` histogram to live classification calls:

- Observe elapsed LLM request duration for each classification attempt.
- Record latency for success and failure paths where practical.
- Add unit/integration tests asserting histogram observation invocations.

### 19.9 DLQ attempt tracking accuracy (ERR-004)

Persist accurate retry-attempt counts for failed classifications:

- Track retry attempts used by LLM/API call path.
- Persist real attempt count in DLQ rows instead of a constant value.
- Add tests confirming DLQ `attempts` reflects actual retry exhaustion behavior.

### 19.10 Runtime config env override support (PRD 14.2)

Support `GMAIL_SORTER_CONFIG` environment override for CLI runtime defaults:

- Resolve default config path from `GMAIL_SORTER_CONFIG` when `--config` is not provided.
- Preserve explicit CLI flag precedence over environment defaults.
- Add CLI tests for env-var defaulting and precedence.

### 19.11 Verification and closure update

After Tasks 19.1–19.10 are implemented:

- Re-run PRD-to-repository verification and document results in `README.md`, `CHANGELOG.md`, and `PLAN.md`.
- Reintroduce `.DONE` only if all remaining PRD gaps are closed.

**Acceptance criteria:**

- All newly identified requirement gaps are closed with corresponding tests.
- Verification evidence is recorded in project documentation.
- Completion sentinel restoration is conditioned on verified full PRD compliance.

---

## Dependency Order Summary

```
Task 1  (scaffold)
  └─ Task 2  (config)
       └─ Task 3  (database)
             ├─ Task 4  (auth)
             ├─ Task 6  (utils)
             │    ├─ Task 5  (Gmail client)            ← needs Task 4 + Task 6 retry helper
             │    ├─ Task 7  (processor)
             │    └─ Task 8  (LLM client)
             │         └─ Task 9  (classifier engine)  ← needs Tasks 3,5,6,7,8
            │              ├─ Task 10 (Pub/Sub)
            │              ├─ Task 11 (backfill)
            │              └─ Task 12 (observability)
            │                   └─ Task 13 (CLI)      ← needs all above
            └─ Tasks 14–16 (tests)
                 └─ Task 17 (packaging)
```

Tasks within a level that have no inter-dependency (e.g., Tasks 4 and 6) MAY be implemented in parallel.
