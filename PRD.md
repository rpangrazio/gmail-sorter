# Gmail Sorting System
Product Requirements Document
Version 1.0  |  April 15, 2026  |  Engineering Team
# 1. Document Metadata


| Field | Value |
| --- | --- |
| Title | Gmail Sorting System — Product Requirements Document |
| Version | 1.0 |
| Date | April 15, 2026 |
| Status | Draft |
| Author | Engineering Team |
| Audience | Software Engineers, Engineering Managers, Technical Stakeholders |
| Classification | Internal — Confidential |

# 2. Executive Summary
The **Gmail Sorting System** is an automated email classification pipeline designed to eliminate manual email triage. The system authenticates with a user's Gmail account via OAuth 2.0, ingests incoming emails in real time through Google Cloud Pub/Sub push notifications, and classifies each message by sending its metadata and body to a configurable Large Language Model (LLM) via GitHub Copilot's API. The LLM provider is GitHub Copilot, while the underlying model is configurable—supporting options such as GPT-4o, Claude, and others. Upon receiving a structured JSON response containing the classification category and confidence score, the system applies the corresponding Gmail label to the message automatically. Additionally, the system supports a --backfill startup flag that triggers a one-time full-mailbox scan, classifying and labeling all existing messages. The entire pipeline is configurable through a single YAML configuration file, covering categories, label mappings, prompt templates, model selection, confidence thresholds, and runtime behavior. This PRD defines the complete set of functional, non-functional, and security requirements necessary for an engineering team to begin implementation.
# 3. Goals and Non-Goals
## 3.1 Goals
- Automate email triage and classification with minimal user intervention.
- Provide real-time classification of incoming emails via Google Cloud Pub/Sub push notifications.
- Allow full configurability of categories, Gmail labels, LLM prompts, and the underlying LLM model.
- Support a one-time full-mailbox scan and classification on first startup via a --backfill flag.
- Use GitHub Copilot as the LLM provider with a configurable model selector (e.g., GPT-4o, Claude Sonnet, GPT-4o-mini).
- Maintain a local audit trail of all classification decisions in a SQLite database.
- Ensure idempotent processing—reprocessing a message MUST NOT create duplicate labels or records.
## 3.2 Non-Goals
- Email composition, sending, or auto-reply functionality.
- Spam filtering—Gmail's built-in spam filter is assumed to be active and sufficient.
- Multi-account management (out of scope for v1).
- A graphical user interface—v1 is CLI and configuration-file driven only.
- Custom LLM provider integrations beyond GitHub Copilot (e.g., Ollama, Azure OpenAI).
- End-user-facing analytics dashboards.
# 4. System Architecture Overview
The Gmail Sorting System is composed of seven core components that operate in a sequential data-flow pipeline. The architecture is designed for modularity, allowing each component to be tested, replaced, or extended independently.
## 4.1 Component Descriptions


| Component | Responsibility |
| --- | --- |
| Gmail API Client | Authenticates with the Gmail API via OAuth 2.0. Reads email messages, retrieves metadata and body content, manages Gmail labels, and applies labels to classified messages. |
| Google Cloud Pub/Sub Listener | Receives real-time push notifications from Google Cloud Pub/Sub when new emails arrive in the authenticated user's inbox. Supports both push (HTTP endpoint) and pull subscription modes. |
| Email Processor | Extracts relevant fields from each email—sender, subject, body snippet, date, and selected headers—and constructs the LLM classification prompt using a configurable Jinja2 template. |
| LLM Classification Engine | Sends the constructed prompt to GitHub Copilot's API (with the model configurable per the config file), receives the structured JSON response containing the category, confidence score, and reasoning, and validates the response against the configured category list. |
| Label Applicator | Maps the returned category to a Gmail label and applies it to the email via the Gmail API. Supports optional archiving (INBOX label removal) and dry-run mode. |
| Configuration Manager | Loads, validates, and provides access to the YAML/JSON configuration file. Validates category uniqueness, required fields, and runtime flags using Pydantic models. |
| Backfill Engine | On startup with the --backfill flag, paginates through the entire mailbox, classifies all unprocessed messages with configurable concurrency, and supports resumable operation if interrupted. |

## 4.2 Data Flow
The end-to-end data flow for real-time classification follows this sequence:
- **Pub/Sub Notification** — Google Cloud Pub/Sub delivers a push notification indicating a new message has arrived in the user's Gmail inbox.
- **Email Fetch** — The Gmail API Client retrieves the full email message (metadata + body) using the message ID from the notification.
- **Idempotency Check** — The system checks whether the message already bears a system-managed label or exists in the classification database. If so, processing is skipped.
- **Prompt Construction** — The Email Processor extracts relevant fields and renders the Jinja2 prompt template with the email data and configured category list.
- **LLM API Call** — The LLM Classification Engine sends the prompt to GitHub Copilot's API using the configured model, with timeout and retry policies enforced.
- **Category Response** — The engine parses the structured JSON response, validates the category against the allowed list, and checks the confidence score against the configured threshold.
- **Label Application** — The Label Applicator maps the validated category to a Gmail label and applies it via gmail.users.messages.modify(). The classification is recorded in the SQLite database.
- **Pub/Sub Acknowledgment** — The Pub/Sub message is acknowledged only after successful label application, ensuring at-least-once processing semantics.


| Note In backfill mode, steps 1 and 8 are replaced by mailbox pagination via gmail.users.messages.list() with pageToken, and processing is parallelized up to the configured concurrency limit. |
| --- |

# 5. Functional Requirements
Requirements use RFC 2119 keywords: **MUST** (mandatory), **SHOULD** (recommended), **MAY** (optional). Each requirement is uniquely identified for traceability.
## 5.1 Authentication & Authorization


| ID | Requirement |
| --- | --- |
| FR-001 | The system MUST authenticate with Gmail using OAuth 2.0 with the following scopes: gmail.readonly, gmail.labels, gmail.modify. |
| FR-002 | The system MUST securely store OAuth refresh tokens encrypted at rest, using OS keyring integration or an encrypted file with restricted file permissions (0600). |
| FR-003 | The system MUST handle token refresh automatically without user intervention. Expired access tokens MUST be refreshed transparently using the stored refresh token. |
| FR-004 | The system MUST support Google Cloud service account authentication for Pub/Sub topic and subscription management. |
| FR-005 | The system MUST validate all required OAuth scopes on startup and exit with a clear, actionable error message if any required scopes are missing. |

## 5.2 Email Ingestion


| ID | Requirement |
| --- | --- |
| FR-010 | The system MUST fetch email metadata and body content via the Gmail API upon receiving a Pub/Sub notification. |
| FR-011 | The system MUST extract the following fields for classification: From, To, Subject, Date, Body (plain text, truncated to a configurable max length, default 4096 characters), List-Unsubscribe header presence (boolean), and Reply-To header. |
| FR-012 | The system MUST handle multipart MIME messages, preferring text/plain over text/html. When only text/html is available, the system MUST perform HTML-to-text conversion as a fallback. |
| FR-013 | The system MUST skip messages already bearing a system-managed label to ensure idempotent processing. |
| FR-014 | The system MUST support configurable batch sizes for Gmail API calls (default: 50 messages per batch). |
| FR-015 | The system MUST respect Gmail API rate limits using exponential backoff with jitter. The system SHOULD log rate-limit events at the WARNING level. |

## 5.3 Google Cloud Pub/Sub Integration


| ID | Requirement |
| --- | --- |
| FR-020 | The system MUST create or reuse a Pub/Sub topic and subscription linked to the authenticated Gmail account. |
| FR-021 | The system MUST call gmail.users.watch() to register for push notifications on the INBOX label. |
| FR-022 | The system MUST renew the watch() registration before expiry (every 7 days) via a scheduled cron job or internal timer. |
| FR-023 | The system MUST process Pub/Sub messages with at-least-once delivery semantics and handle duplicate messages idempotently. |
| FR-024 | The system MUST acknowledge Pub/Sub messages only after successful label application, ensuring no messages are lost in the event of processing failure. |
| FR-025 | The system MUST support both push (HTTP endpoint) and pull subscription modes, configurable via the configuration file. |
| FR-026 | The system MUST log all Pub/Sub message processing outcomes (success, skip, error) with the Pub/Sub message ID and the Gmail message ID. |

## 5.4 LLM Classification


| ID | Requirement |
| --- | --- |
| FR-030 | The system MUST use GitHub Copilot as the LLM provider, calling its API endpoint for all classification requests. |
| FR-031 | The system MUST support a configurable model field in the configuration file (e.g., gpt-4o, claude-sonnet-4, gpt-4o-mini). |
| FR-032 | The system MUST construct classification prompts using a configurable prompt template supporting Jinja2 syntax. |
| FR-033 | The prompt template MUST support the following variables: {{sender}}, {{subject}}, {{body}}, {{date}}, {{headers}}, and {{categories}} (the list of valid categories with descriptions). |
| FR-034 | The system MUST instruct the LLM to return a structured JSON response: {"category": "<category_name>", "confidence": <0.0-1.0>, "reasoning": "<brief explanation>"}. |
| FR-035 | The system MUST validate the LLM response against the configured category list. If the returned category is not in the list, the system MUST apply a configurable fallback label (default: uncategorized). |
| FR-036 | The system MUST support a configurable confidence threshold (default: 0.7). Classifications below the threshold MUST be routed to the fallback label. |
| FR-037 | The system MUST enforce a configurable timeout for LLM API calls (default: 30 seconds). |
| FR-038 | The system MUST retry failed LLM API calls up to a configurable number of times (default: 3) with exponential backoff. |
| FR-039 | The system MUST log the full prompt and response for auditability. Prompt/response logging MUST be redactable via a configuration flag (default: redacted). |
| FR-040 | The system MUST support a configurable system_prompt field that sets the LLM's system-level instruction for all classification requests. |

## 5.5 Configurable Categories & Labels


| ID | Requirement |
| --- | --- |
| FR-050 | The system MUST support a configurable list of categories, each mapped to a Gmail label name. |
| FR-051 | Each category entry MUST include: name (internal identifier), label (Gmail label string, supporting nested labels like AutoSort/Marketing), and description (used in the LLM prompt to describe the category). |
| FR-052 | The system MUST auto-create Gmail labels on startup if they do not already exist in the user's account. |
| FR-054 | The system MUST support adding custom categories via the configuration file without requiring code changes. |
| FR-055 | The system MUST support multi-label classification (an email can receive more than one category label) as a configurable option (default: single-label mode). |
| FR-056 | The system MUST validate that no two categories map to the same Gmail label on startup and exit with a descriptive error if a conflict is detected. |

**FR-053:** The system MUST ship with the following default categories. All categories are configurable and overridable via the configuration file:


| Category Name | Default Gmail Label | Description |
| --- | --- | --- |
| marketing | AutoSort/Marketing | Promotional emails from brands, companies, or services advertising products, sales, or events. |
| cold_emails | AutoSort/Cold Emails | Unsolicited outreach from individuals or companies seeking business, partnerships, or sales. |
| junk | AutoSort/Junk | Low-value or irrelevant emails that are not spam but offer no actionable content. |
| newsletters | AutoSort/Newsletters | Recurring subscription-based content digests, industry news, or editorial emails. |
| to_reply | AutoSort/To Reply | Emails from known contacts or threads requiring a personal response or action. |
| alerts | AutoSort/Alerts | Automated notifications from services, monitoring systems, CI/CD pipelines, or security alerts. |
| billing | AutoSort/Billing | Invoices, payment confirmations, subscription charges, or payment-due notices. |
| receipts | AutoSort/Receipts | Purchase confirmations, order summaries, shipping notifications, or delivery updates. |

## 5.6 Label Application


| ID | Requirement |
| --- | --- |
| FR-060 | The system MUST apply the classified Gmail label to the email via gmail.users.messages.modify(). |
| FR-061 | The system MUST NOT remove any existing user-applied labels when applying a classification label. |
| FR-062 | The system MUST support a configurable option to archive (remove the INBOX label from) classified messages (default: false). |
| FR-063 | The system MUST support a dry-run mode that logs intended classifications without applying any labels to messages. |
| FR-064 | The system MUST record each classification action in a local SQLite database with the following fields: message_id, timestamp, category, confidence, model_used, prompt_hash, label_applied. |

## 5.7 Full-Mailbox Backfill


| ID | Requirement |
| --- | --- |
| FR-070 | The system MUST support a --backfill CLI flag that triggers a full-mailbox scan on startup. |
| FR-071 | In backfill mode, the system MUST paginate through all messages using gmail.users.messages.list() with pageToken. |
| FR-072 | The system MUST skip messages that already have a system-managed label (idempotent reprocessing). |
| FR-073 | The system MUST support a configurable concurrency limit for backfill processing (default: 5 concurrent classifications). |
| FR-074 | The system MUST support resumable backfill. If interrupted, backfill MUST resume from the last processed message ID, tracked in the local SQLite database. |
| FR-075 | The system MUST log backfill progress (processed/total) at configurable intervals (default: every 100 messages). |

# 6. Configuration Schema
The following is the complete YAML configuration file with all configurable fields, default values, and inline documentation. The configuration is validated on startup using Pydantic models (**FR-056**, **FR-005**).
# =============================================================================
# Gmail Sorting System — Configuration File
# =============================================================================
# File: config.yaml
# Docs: See PRD Section 6 for field definitions and constraints.
# =============================================================================

# -----------------------------------------------------------------------------
# Gmail API Settings
# -----------------------------------------------------------------------------
gmail:
  # Path to the OAuth 2.0 client credentials JSON file downloaded from
  # Google Cloud Console.
  credentials_path: "./credentials.json"

  # Path where the authenticated OAuth token will be stored.
  # File permissions will be set to 0600 automatically.
  token_path: "./token.json"

  # OAuth 2.0 scopes required by the system.
  # Do not modify unless you understand the implications.
  scopes:
    - "https://www.googleapis.com/auth/gmail.readonly"
    - "https://www.googleapis.com/auth/gmail.labels"
    - "https://www.googleapis.com/auth/gmail.modify"

# -----------------------------------------------------------------------------
# Google Cloud Pub/Sub Settings
# -----------------------------------------------------------------------------
pubsub:
  # Google Cloud project ID where the Pub/Sub topic resides.
  project_id: "my-gcp-project-id"

  # Pub/Sub topic name. Will be created if it does not exist.
  topic: "gmail-notifications"

  # Pub/Sub subscription name. Will be created if it does not exist.
  subscription: "gmail-sorter-subscription"

  # Subscription mode: "push" (HTTP endpoint) or "pull" (long-polling).
  mode: "pull"  # Options: push | pull

# -----------------------------------------------------------------------------
# LLM Provider Settings
# -----------------------------------------------------------------------------
llm:
  # LLM provider identifier. Currently only "github_copilot" is supported.
  provider: "github_copilot"

  # Model to use for classification. Must be available via the provider.
  model: "gpt-4o"  # Examples: gpt-4o, claude-sonnet-4, gpt-4o-mini

  # Name of the environment variable containing the API key.
  # The key itself MUST NOT be stored in this file (SEC-002).
  api_key_env: "GITHUB_COPILOT_API_KEY"

  # Timeout in seconds for each LLM API call.
  timeout_seconds: 30

  # Maximum number of retry attempts for failed LLM API calls.
  max_retries: 3

  # System-level prompt sent to the LLM to establish its role.
  system_prompt: |
    You are an expert email classification assistant. Your task is to
    categorize emails into predefined categories based on their content,
    sender, subject, and metadata. You must respond with valid JSON only.

  # Path to a Jinja2 template file for the user prompt, OR an inline
  # template string. If a file path is provided, it takes precedence.
  prompt_template: "./prompts/classify_email.j2"

# -----------------------------------------------------------------------------
# Classification Settings
# -----------------------------------------------------------------------------
classification:
  # Minimum confidence threshold (0.0 to 1.0). Classifications below
  # this threshold are routed to the fallback category.
  confidence_threshold: 0.7

  # Category applied when the LLM returns an unrecognized category
  # or a confidence score below the threshold.
  fallback_category: "uncategorized"

  # Enable multi-label classification. When true, the LLM may return
  # multiple categories for a single email.
  multi_label: false

# -----------------------------------------------------------------------------
# Category Definitions
# -----------------------------------------------------------------------------
# Each category requires: name, label, and description.
# - name:        Internal identifier (lowercase, underscores).
# - label:       Gmail label to apply (supports nested: "Parent/Child").
# - description: Used in the LLM prompt to describe what belongs here.
# -----------------------------------------------------------------------------
categories:
  - name: "marketing"
    label: "AutoSort/Marketing"
    description: >
      Promotional emails from brands, companies, or services advertising
      products, sales, or events.

  - name: "cold_emails"
    label: "AutoSort/Cold Emails"
    description: >
      Unsolicited outreach from individuals or companies seeking business,
      partnerships, or sales.

  - name: "junk"
    label: "AutoSort/Junk"
    description: >
      Low-value or irrelevant emails that are not spam but offer no
      actionable content.

  - name: "newsletters"
    label: "AutoSort/Newsletters"
    description: >
      Recurring subscription-based content digests, industry news, or
      editorial emails.

  - name: "to_reply"
    label: "AutoSort/To Reply"
    description: >
      Emails from known contacts or threads requiring a personal response
      or action.

  - name: "alerts"
    label: "AutoSort/Alerts"
    description: >
      Automated notifications from services, monitoring systems, CI/CD
      pipelines, or security alerts.

  - name: "billing"
    label: "AutoSort/Billing"
    description: >
      Invoices, payment confirmations, subscription charges, or
      payment-due notices.

  - name: "receipts"
    label: "AutoSort/Receipts"
    description: >
      Purchase confirmations, order summaries, shipping notifications,
      or delivery updates.

# -----------------------------------------------------------------------------
# Processing Settings
# -----------------------------------------------------------------------------
processing:
  # Maximum number of characters from the email body to include in
  # the LLM prompt.
  body_max_length: 4096

  # Number of messages to fetch per Gmail API batch request.
  batch_size: 50

  # Maximum number of concurrent classification tasks during backfill.
  backfill_concurrency: 5

  # If true, remove the INBOX label after applying the classification label.
  archive_after_label: false

  # If true, log classifications without applying Gmail labels.
  dry_run: false

# -----------------------------------------------------------------------------
# Logging Settings
# -----------------------------------------------------------------------------
logging:
  # Log level: DEBUG, INFO, WARNING, ERROR, CRITICAL
  level: "INFO"

  # If true, include full LLM prompts and responses in logs.
  # WARNING: May contain sensitive email content. See SEC-007.
  log_prompts: false

# -----------------------------------------------------------------------------
# Database Settings
# -----------------------------------------------------------------------------
database:
  # Path to the SQLite database file for classification tracking.
  path: "./gmail_sorter.db"
# 7. Non-Functional Requirements


| ID | Requirement | Target |
| --- | --- | --- |
| NFR-001 | End-to-end classification latency (Pub/Sub receipt to label applied) MUST be within target at the 95th percentile. | < 10 seconds (p95) |
| NFR-002 | Backfill mode MUST sustain minimum message processing throughput with default concurrency settings. | ≥ 500 messages/minute |
| NFR-003 | The Pub/Sub listener MUST maintain target uptime with automatic reconnection on transient failures. | 99.9% availability |
| NFR-004 | Classification logs in the SQLite database MUST be retained for the configurable retention period. | 90 days (configurable) |
| NFR-005 | Reprocessing the same message MUST NOT create duplicate labels or database entries. | Full idempotency |
| NFR-006 | The system MUST run on Linux, macOS, and Windows. | Python 3.11+ |
| NFR-007 | Idle memory consumption (listener active, no messages processing) MUST remain under target. | < 256 MB RSS |

# 8. Security Requirements


| ID | Requirement |
| --- | --- |
| SEC-001 | OAuth tokens MUST be encrypted at rest using OS keyring integration (e.g., macOS Keychain, Windows Credential Manager, Linux Secret Service) or an encrypted file with restricted file permissions (0600). |
| SEC-002 | The LLM API key MUST be loaded from an environment variable specified in the config file (llm.api_key_env). The API key MUST NOT be stored directly in the configuration file or in version control. |
| SEC-003 | Email body content sent to the LLM MUST be stripped of any embedded images (base64 or linked), attachments, and tracking pixels before prompt construction. |
| SEC-004 | The system MUST support an allowlist and blocklist of sender domains to include or exclude from LLM processing. Blocklisted domains MUST be skipped without API calls. |
| SEC-005 | All HTTP communications (Gmail API, Pub/Sub, LLM API) MUST use TLS 1.2 or higher. The system MUST reject connections using older TLS versions. |
| SEC-006 | The local SQLite database MUST NOT store raw email content (body, subject, sender). Only message IDs, classification results, confidence scores, and processing metadata are permitted. |
| SEC-007 | Logs MUST redact email body content by default. Full prompt and response logging MUST require explicit opt-in via the logging.log_prompts configuration flag. |

# 9. Error Handling & Observability


| ID | Requirement |
| --- | --- |
| ERR-001 | All errors MUST be categorized into one of the following types: auth_error, api_error, llm_error, config_error, pubsub_error. Error types MUST be included in all log entries and metric labels. |
| ERR-002 | The system MUST emit structured JSON logs compatible with standard log aggregators (e.g., ELK, Datadog, CloudWatch). Each log entry MUST include: timestamp, level, error_type, message, and context (message ID, operation). |
| ERR-003 | The system MUST expose optional Prometheus-compatible metrics via an HTTP endpoint: emails_processed_total, emails_classified_total (by category), classification_errors_total, llm_latency_seconds (histogram), pubsub_messages_received_total. |
| ERR-004 | The system MUST implement a dead-letter queue (DLQ) for messages that fail classification after all configured retry attempts. DLQ entries MUST be stored in the SQLite database with error details. |
| ERR-005 | The system MUST support optional webhook notifications for critical errors. The webhook URL is configurable, and payloads MUST include error type, message ID, timestamp, and a human-readable description. |

# 10. API & CLI Interface
The system exposes a command-line interface (CLI) built with Click. The CLI is the primary interface for all operations in v1.
## 10.1 Commands


| Command | Description |
| --- | --- |
| gmail-sorter run | Start the Pub/Sub listener for real-time email classification. Runs continuously until interrupted. |
| gmail-sorter run --backfill | Start the real-time listener AND perform an initial full-mailbox backfill concurrently. |
| gmail-sorter backfill | Run a one-time full-mailbox backfill only, then exit upon completion. |
| gmail-sorter validate-config | Validate the configuration file against the schema and exit. Reports all validation errors. |
| gmail-sorter auth | Run the OAuth 2.0 authentication flow interactively. Opens a browser for consent and stores the token. |
| gmail-sorter stats | Print classification statistics from the local SQLite database (total processed, by category, by date range, error rate). |

## 10.2 Global Flags


| Flag | Description |
| --- | --- |
| --config <path> | Path to the configuration file. Default: ./config.yaml |
| --dry-run | Override the config to enable dry-run mode. No labels are applied. |
| --log-level <level> | Override the configured log level. Accepts: DEBUG, INFO, WARNING, ERROR, CRITICAL. |
| --version | Print the application version and exit. |

# 11. Database Schema
The system uses a local SQLite database for classification tracking, backfill state management, and dead-letter queue persistence. The schema consists of three tables:
-- =============================================================================
-- Gmail Sorting System — SQLite Database Schema
-- =============================================================================

-- Classification audit log
-- Records every classification decision for auditability and idempotency.
CREATE TABLE IF NOT EXISTS classifications (
    message_id          TEXT PRIMARY KEY,
    gmail_thread_id     TEXT NOT NULL,
    timestamp           TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    category            TEXT NOT NULL,
    confidence          REAL NOT NULL CHECK (confidence >= 0.0 AND confidence <= data-id="633" 1.0),
    model_used          TEXT NOT NULL,
    prompt_template_hash TEXT NOT NULL,
    label_applied       TEXT NOT NULL,
    processing_duration_ms INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX idx_classifications_timestamp ON classifications(timestamp);
CREATE INDEX idx_classifications_category ON classifications(category);

-- Backfill state tracker
-- Enables resumable backfill across restarts or interruptions.
CREATE TABLE IF NOT EXISTS backfill_state (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    last_page_token     TEXT,
    last_message_id     TEXT,
    status              TEXT NOT NULL CHECK (status IN ('running', 'completed', 'interrupted'))
                        DEFAULT 'running',
    started_at          TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    completed_at        TEXT,
    total_processed     INTEGER NOT NULL DEFAULT 0,
    total_skipped       INTEGER NOT NULL DEFAULT 0
);

-- Dead-letter queue
-- Stores messages that failed classification after all retry attempts.
CREATE TABLE IF NOT EXISTS dead_letter_queue (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    message_id          TEXT NOT NULL,
    error_type          TEXT NOT NULL,
    error_message       TEXT NOT NULL,
    attempts            INTEGER NOT NULL DEFAULT 0,
    first_failed_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    last_failed_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE INDEX idx_dlq_message_id ON dead_letter_queue(message_id);
CREATE INDEX idx_dlq_error_type ON dead_letter_queue(error_type);
# 12. Default Prompt Template
The system uses a two-part prompt structure: a **system prompt** that establishes the LLM's role and output format, and a **user prompt template** (Jinja2) that is rendered per-email with the extracted fields and category definitions.
## 12.1 System Prompt
You are an expert email classification assistant. Your task is to categorize
an email into exactly one of the predefined categories based on its content,
sender, subject line, and metadata.

Rules:
1. You MUST respond with valid JSON only — no markdown, no explanation
   outside the JSON.
2. The JSON response MUST follow this exact schema:
   {
     "category": "<category_name>",
     "confidence": <float between 0.0 and 1.0>,
     "reasoning": "<one sentence explaining the classification>"
   }
3. The "category" field MUST be one of the category names provided in
   the user prompt. If uncertain, use the category that best fits and
   reflect your uncertainty in the confidence score.
4. The "confidence" field MUST be a float between 0.0 and 1.0 representing
   your certainty in the classification.
5. Do NOT invent categories. Only use categories from the provided list.
## 12.2 User Prompt Template (Jinja2)
Classify the following email into one of the categories listed below.

---

**Email Metadata:**
- From: {{ sender }}
- Subject: {{ subject }}
- Date: {{ date }}
- Has List-Unsubscribe Header: {{ headers.list_unsubscribe | default('No') }}
- Reply-To: {{ headers.reply_to | default('N/A') }}

**Email Body:**
{{ body }}

---

**Available Categories:**
{% for cat in categories %}
- {{ cat.name }}: {{ cat.description }}
{% endfor %}

---

Respond with a JSON object containing "category", "confidence", and "reasoning".
# 13. Dependencies & Technology Stack


| Dependency | Version | Purpose |
| --- | --- | --- |
| Python | 3.11+ | Runtime environment. Required for asyncio task groups and modern type hint support. |
| google-api-python-client | ≥ 2.100 | Gmail API client for reading messages, managing labels, and modifying messages. |
| google-auth-oauthlib | ≥ 1.2 | OAuth 2.0 authentication flow for Gmail API access. |
| google-cloud-pubsub | ≥ 2.18 | Google Cloud Pub/Sub client for receiving real-time email notifications. |
| Jinja2 | ≥ 3.1 | Templating engine for constructing configurable LLM prompts. |
| httpx | ≥ 0.27 | Async HTTP client for LLM API calls to GitHub Copilot. Supports HTTP/2 and connection pooling. |
| sqlite3 | stdlib | Local database for classification audit logs, backfill state, and dead-letter queue. |
| Click | ≥ 8.1 | CLI framework for command parsing, flag handling, and help text generation. |
| Pydantic | ≥ 2.5 | Configuration file validation, type coercion, and settings management. |
| prometheus-client | ≥ 0.20 | Optional. Exposes Prometheus-compatible metrics via an HTTP endpoint for monitoring. |

# 14. Deployment & Operations
## 14.1 Containerized Deployment (Docker)
The primary deployment model is a Docker container running the Pub/Sub listener as a long-lived process. The container image is built using a multi-stage Dockerfile for minimal image size.
### Dockerfile Outline
# Stage 1: Build
FROM python:3.12-slim AS builder
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim
WORKDIR /app
COPY --from=builder /install /usr/local
COPY . .

# Create non-root user
RUN useradd --create-home appuser
USER appuser

# Health check endpoint (see 14.3)
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')"

ENTRYPOINT ["gmail-sorter"]
CMD ["run"]
## 14.2 Required Environment Variables


| Variable | Description |
| --- | --- |
| GITHUB_COPILOT_API_KEY | API key for GitHub Copilot LLM access. Required. |
| GOOGLE_APPLICATION_CREDENTIALS | Path to Google Cloud service account JSON for Pub/Sub. Required for push mode. |
| GMAIL_SORTER_CONFIG | Override path to config file. Optional (default: ./config.yaml). |

## 14.3 Health Check Endpoint
When running in container or server mode, the system MUST expose an HTTP health check endpoint at /health on a configurable port (default: 8080). The endpoint MUST return:
- **HTTP 200** with {"status": "healthy", "pubsub_connected": true, "last_message_at": "..."} when the listener is active and responsive.
- **HTTP 503** with {"status": "unhealthy", "reason": "..."} when the Pub/Sub connection is lost or the system is in an error state.
## 14.4 Bare-Metal Deployment (systemd)
For bare-metal Linux deployments, a systemd unit file is provided to run the listener as a managed service:
[Unit]
Description=Gmail Sorting System
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=gmail-sorter
Group=gmail-sorter
WorkingDirectory=/opt/gmail-sorter
ExecStart=/opt/gmail-sorter/venv/bin/gmail-sorter run
Restart=always
RestartSec=10
Environment=GITHUB_COPILOT_API_KEY=
EnvironmentFile=/opt/gmail-sorter/.env

# Security hardening
NoNewPrivileges=true
ProtectSystem=strict
ProtectHome=true
ReadWritePaths=/opt/gmail-sorter/data

[Install]
WantedBy=multi-user.target
# 15. Testing Strategy
Testing is structured in four tiers to ensure comprehensive coverage of the classification pipeline and supporting infrastructure.
## 15.1 Unit Tests
- **Prompt Construction:** Verify Jinja2 template rendering with various email metadata combinations, edge cases (empty fields, Unicode characters, extremely long bodies), and variable injection.
- **Response Parsing:** Validate JSON response parsing, handling of malformed responses, missing fields, out-of-range confidence values, and unrecognized categories.
- **Configuration Validation:** Test Pydantic model validation for all config fields, including duplicate label detection, missing required fields, type coercion, and invalid values.
- **MIME Parsing:** Test multipart message handling, HTML-to-text fallback, body truncation, and attachment stripping.
- **Idempotency Logic:** Verify that messages with existing system labels are correctly skipped.
## 15.2 Integration Tests
- **Gmail API Sandbox:** Test OAuth flow, message listing, label creation, and label application against the Gmail API sandbox environment.
- **Pub/Sub Integration:** Verify topic/subscription creation, watch registration, message receipt, and acknowledgment using the Pub/Sub emulator.
- **SQLite Operations:** Test database creation, record insertion, idempotent upserts, backfill state persistence, and DLQ operations.
## 15.3 End-to-End Tests
- **Mock LLM Responses:** Full pipeline tests using a mock HTTP server that returns predetermined LLM responses. Covers the complete flow from Pub/Sub notification to label application.
- **Dry-Run Validation:** Verify that dry-run mode logs classifications without making any Gmail API modification calls.
- **Error Scenarios:** Test behavior under LLM timeouts, invalid responses, rate limiting, network failures, and authentication expiry.
## 15.4 Load & Performance Tests
- **Backfill Throughput:** Verify that backfill mode achieves ≥ 500 messages/minute (**NFR-002**) with default concurrency settings.
- **Memory Profiling:** Confirm idle memory stays below 256 MB (**NFR-007**) during sustained listener operation.
- **Latency Benchmarks:** Measure end-to-end classification latency under various load conditions to validate the < 10 second p95 target (**NFR-001**).


| Coverage Target The core classification pipeline (Email Processor, LLM Classification Engine, Label Applicator) MUST achieve ≥ 90% code coverage. Supporting infrastructure (CLI, config loading, database operations) SHOULD achieve ≥ 80% coverage. |
| --- |

# 16. Future Considerations (Out of Scope for v1)
The following features are explicitly out of scope for v1 but are anticipated for future iterations. They are documented here to inform architectural decisions that should not preclude their implementation.
- **Web UI Dashboard:** A browser-based dashboard for viewing classification analytics, reviewing DLQ entries, and adjusting categories in real time.
- **Multi-Account Support:** Ability to manage and classify emails across multiple Gmail accounts from a single deployment.
- **Custom LLM Provider Plugins:** A plugin architecture supporting additional LLM providers such as Ollama (local), Azure OpenAI, Amazon Bedrock, and self-hosted models.
- **User Feedback Loop:** A mechanism for users to manually re-classify emails, with corrections used to refine prompt templates or fine-tune classification accuracy over time.
- **Calendar Integration:** Automatic detection and special handling of meeting-related emails (invitations, RSVPs, agenda updates).
- **Mobile Push Notifications:** Real-time mobile notifications for emails classified as to_reply or other high-priority categories.
- **Auto-Reply Drafts:** LLM-generated reply drafts for common email categories, stored as Gmail drafts for user review.
- **Rule-Based Pre-Filters:** Lightweight regex or rule-based filters that bypass LLM classification for deterministic patterns (e.g., known billing senders).
# 17. Glossary


| Term | Definition |
| --- | --- |
| Backfill | A one-time batch operation that processes all existing messages in a mailbox, applying classification labels retroactively to messages received before the system was deployed. |
| Pub/Sub | Google Cloud Pub/Sub, an asynchronous messaging service that enables decoupled communication between services. Used here to receive real-time notifications when new emails arrive. |
| OAuth 2.0 | An industry-standard authorization framework that enables third-party applications to access a user's resources (e.g., Gmail) without exposing the user's credentials. |
| LLM | Large Language Model. A neural network trained on large text corpora capable of understanding and generating natural language. Used here for email classification. |
| Dead-Letter Queue (DLQ) | A holding area for messages that could not be processed successfully after all retry attempts. DLQ entries are stored for manual review and reprocessing. |
| Idempotency | A property ensuring that performing the same operation multiple times produces the same result as performing it once. In this system, reprocessing a message does not create duplicate labels or database records. |
| Jinja2 | A Python templating engine that enables dynamic content generation using template variables, filters, and control structures. Used here for constructing configurable LLM prompts. |
| Exponential Backoff | A retry strategy where the wait time between successive retry attempts increases exponentially (e.g., 1s, 2s, 4s, 8s), optionally with random jitter, to reduce load on failing services. |

# 18. Revision History


| Version | Date | Author | Changes |
| --- | --- | --- | --- |
| 1.0 | April 15, 2026 | Engineering Team | Initial draft. Complete functional requirements, architecture overview, configuration schema, database schema, security requirements, and deployment guide. |

— End of Document —
