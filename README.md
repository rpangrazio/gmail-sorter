# Gmail AI Sorter

An AI-powered Gmail agent that automatically classifies incoming emails into
user-defined categories and applies Gmail labels. It uses
[GitHub Copilot](https://github.com/features/copilot) for classification and
[Google Cloud Pub/Sub](https://cloud.google.com/pubsub) for real-time
Gmail push notifications.

## Table of Contents

- [How It Works](#how-it-works)
- [Prerequisites](#prerequisites)
- [GCP Setup](#gcp-setup)
- [Installation](#installation)
- [Configuration](#configuration)
- [Running the Agent](#running-the-agent)
- [Customizing Categories](#customizing-categories)
- [Monitoring and Logs](#monitoring-and-logs)
- [Development](#development)
- [Troubleshooting](#troubleshooting)
- [Project Structure](#project-structure)

---

## How It Works

```
Gmail Inbox (new email arrives)
        │
        ▼
Gmail Watch API ──publishes──► GCP Pub/Sub Topic
                                        │
                              Agent pulls notification
                                        │
                              Gmail History API ──fetches new messages──►
                                        │
                              GitHub Copilot API ──classifies email──►
                                        │
                              Gmail Labels API ──applies label──►
                                        │
                              State Manager ──persists history cursor
```

1. **Gmail Watch**: The agent registers a "watch" on your Gmail inbox via
   the Gmail API. Gmail publishes a small notification to a Cloud Pub/Sub
   topic whenever your mailbox changes.

2. **Pub/Sub Pull**: The agent uses a *pull* subscription — it polls the
   subscription endpoint at regular intervals. No public HTTPS endpoint
   is required, making this ideal for a private Docker container.

3. **History API**: Each Pub/Sub notification contains only a `historyId`.
   The agent calls `users.history.list(startHistoryId=lastKnownId)` to find
   all new inbox messages since the last processed event.

4. **Copilot Classification**: The subject, sender, and body of each new email
   are sent to GitHub Copilot's chat-completion API (`gpt-4o` by default). The
   AI returns a single category name based on the descriptions in your config.

5. **Label Application**: The matching Gmail label is applied to the email.
   Nested labels (e.g., `AI-Sorted/Work`) are created automatically if they
   don't exist.

6. **Watch Renewal**: Gmail watches expire after 7 days. A background thread
   renews the watch automatically every 6 days.

7. **Crash Recovery**: The last-processed history cursor is persisted to the
   configured state backend (JSON file, SQLite, or PostgreSQL). On restart the
   agent resumes exactly where it left off.

---

## Prerequisites

| Requirement | Notes |
|---|---|
| Docker & Docker Compose | Docker ≥ 20, Compose ≥ 2.0 |
| Google account | Any Gmail account |
| Google Cloud Project | Free tier is sufficient |
| GitHub account | Must have an active [GitHub Copilot](https://github.com/features/copilot) subscription |
| GitHub personal access token | See [Installation](#installation) step 3 |

---

## GCP Setup

You need a Google Cloud Project with the Gmail and Pub/Sub APIs enabled, an
OAuth2 client, a Pub/Sub topic, and a pull subscription.

### Automated setup (recommended)

If you have the `gcloud` CLI installed and authenticated:

```bash
GCP_PROJECT=my-gcp-project-id ./scripts/setup_gcp.sh
```

This script creates the topic, subscription, and IAM binding automatically.

### Manual setup

#### 1. Create or select a GCP project

Go to [Google Cloud Console](https://console.cloud.google.com/) and create
a new project or select an existing one.

#### 2. Enable APIs

```bash
gcloud services enable gmail.googleapis.com pubsub.googleapis.com \
  --project=YOUR_PROJECT_ID
```

Or via Console: **APIs & Services → Library** → search for and enable
"Gmail API" and "Cloud Pub/Sub API".

#### 3. Create OAuth2 credentials

1. Go to **APIs & Services → Credentials**.
2. Click **+ Create Credentials → OAuth 2.0 Client ID**.
3. Choose **Desktop App** as the application type.
4. Download the JSON file and save it as `./credentials/credentials.json`.

> **Important**: Also configure the OAuth consent screen
> (APIs & Services → OAuth consent screen) if prompted.  Add your Gmail
> address as a test user.

#### 4. Create a Pub/Sub topic

```bash
gcloud pubsub topics create gmail-sorter --project=YOUR_PROJECT_ID
```

#### 5. Create a pull subscription

```bash
gcloud pubsub subscriptions create gmail-sorter-sub \
  --topic=gmail-sorter \
  --project=YOUR_PROJECT_ID \
  --ack-deadline=60 \
  --message-retention-duration=7d
```

#### 6. Grant Gmail permission to publish to the topic

Gmail uses a fixed service account to deliver push notifications.  You must
grant it the Publisher role on your topic:

```bash
gcloud pubsub topics add-iam-policy-binding gmail-sorter \
  --project=YOUR_PROJECT_ID \
  --member="serviceAccount:gmail-api-push@system.gserviceaccount.com" \
  --role="roles/pubsub.publisher"
```

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/rpangrazio/gmail-sorter.git
cd gmail-sorter
```

### 2. Place your OAuth2 credentials

```bash
cp /path/to/downloaded-credentials.json ./credentials/credentials.json
```

### 3. Create your environment file

```bash
cp .env.example .env
```

Edit `.env` and set your GitHub personal access token.  The token must belong
to an account with an active GitHub Copilot subscription:

```
GITHUB_TOKEN=ghp_...
```

You can create a token at **GitHub → Settings → Developer settings →
Personal access tokens → Tokens (classic)**.  No specific scopes are
required beyond the default read access — Copilot access is determined by
your subscription, not by token scopes.

### 4. Edit the configuration

```bash
nano config/config.yaml
```

At minimum, update the GCP fields:

```yaml
google_project_id: "your-actual-project-id"
pubsub_subscription: "projects/your-actual-project-id/subscriptions/gmail-sorter-sub"
gmail_watch_topic: "projects/your-actual-project-id/topics/gmail-sorter"
```

---

## Running the Agent

### Step 1 — First-time OAuth2 authorization

This step is required **once** and opens a browser window (or prints a URL
if running headlessly) for you to grant Gmail access to the agent.

```bash
docker-compose run --rm sorter python -m src.main --setup
```

Follow the on-screen instructions.  After authorization the token is saved
to the `gmail-sorter-data` Docker volume and the container exits.

### Step 2 — Start the agent

```bash
docker-compose up -d
```

### View live logs

```bash
docker-compose logs -f
```

### Stop the agent

```bash
docker-compose down
```

---

## Configuration

All agent behaviour is controlled by `config/config.yaml`.

### Core settings

| Field | Required | Default | Description |
|---|---|---|---|
| `google_project_id` | ✅ | — | GCP project ID |
| `pubsub_subscription` | ✅ | — | Full Pub/Sub subscription resource path |
| `gmail_watch_topic` | ✅ | — | Full Pub/Sub topic resource path |
| `categories` | ✅ | — | List of email categories (see below) |
| `max_emails_per_poll` | ❌ | `10` | Max emails per Pub/Sub pull cycle |
| `log_level` | ❌ | `INFO` | Verbosity: `DEBUG` / `INFO` / `WARNING` / `ERROR` |
| `dry_run` | ❌ | `false` | Classify without applying labels |

### AI provider

| Field | Required | Default | Description |
|---|---|---|---|
| `ai_provider` | ❌ | `copilot` | AI backend: `copilot` or `openai` |
| `copilot_model` | ❌ | `gpt-4o` | Model used when `ai_provider = copilot` |
| `openai_model` | ❌ | `gpt-4o` | Model used when `ai_provider = openai` |

**`copilot`** sends requests to `https://api.githubcopilot.com` using
`GITHUB_TOKEN`.  Supported models include `gpt-4o`, `gpt-4o-mini`, and
`o3-mini`.

**`openai`** uses the official OpenAI API (or any compatible endpoint via
`OPENAI_BASE_URL`) with `OPENAI_API_KEY`.

### State backend

| Field | Required | Default | Description |
|---|---|---|---|
| `state_backend` | ❌ | `json` | Persistence backend: `json`, `sqlite`, or `postgres` |

| Backend | Env var needed | Notes |
|---|---|---|
| `json` | — | Atomic JSON file at `STATE_FILE_PATH` (default `/data/state.json`) |
| `sqlite` | — | SQLite database at `SQLITE_DB_PATH` (default `/data/gmail_sorter.db`) |
| `postgres` | `DATABASE_URL` | PostgreSQL connection URL; enable the `postgres` service in `docker-compose.yml` |

The config file is mounted read-only into the container.  Changes take
effect after a container restart:

```bash
docker-compose restart sorter
```

---

## Customizing Categories

Categories are defined in the `categories` list in `config.yaml`.  Each
entry has:

```yaml
categories:
  - name: "work"              # Unique lowercase identifier
    label: "AI-Sorted/Work"  # Gmail label (/ for nesting, created if missing)
    description: >           # Shown to the AI — be specific and descriptive
      Professional emails: meeting invites, project updates, client comms.
    keywords:                # Optional hints for the AI
      - meeting
      - invoice
```

**Tips for writing good descriptions:**

- Mention the *sender types* (e.g., "from colleagues or clients").
- Mention *subject line patterns* (e.g., "Subject often contains 'Invoice #'").
- Note any *unique signals* (e.g., "always has an unsubscribe link").
- Put more specific categories **before** general ones.

**Test your categories first** by setting `dry_run: true` in the config,
starting the agent, and watching the logs.  The log line

```
[INFO] Classification result: 'work' (subject: 'Q3 budget review')
```

shows what label *would* be applied without actually changing anything.
Switch `dry_run: false` when satisfied.

---

## Monitoring and Logs

All output is written to `stdout` in this format:

```
2026-03-31 09:15:32 [INFO] src.main: Processing message 18e1a2b3c4 | From: boss@company.com | Subject: Q3 review
2026-03-31 09:15:33 [INFO] src.classifier: [copilot] Classification result: 'work' (subject: 'Q3 review')
2026-03-31 09:15:33 [INFO] src.main: Labelled message 18e1a2b3c4 as 'work' (label: 'AI-Sorted/Work').
```

### Log levels

| Level | Use case |
|---|---|
| `DEBUG` | Verbose output including all API calls |
| `INFO` | Normal operation — one line per email processed (recommended) |
| `WARNING` | Non-fatal issues (transient API errors, unknown classifications) |
| `ERROR` | Failures that prevented an email from being labelled |

### Accessing logs

```bash
# Live tail
docker-compose logs -f

# Last 100 lines
docker-compose logs --tail=100 sorter

# Save to file
docker-compose logs sorter > sorter.log
```

---

## Development

### Local setup (without Docker)

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # fill in GITHUB_TOKEN
python -m src.main --setup  # authorize OAuth2 (using local credentials path)
python -m src.main          # run locally
```

When running locally, set the path variables in `.env` to point to your
local `credentials/` and `data/` directories:

```env
GOOGLE_CREDENTIALS_PATH=./credentials/credentials.json
GOOGLE_TOKEN_PATH=./data/token.json
STATE_FILE_PATH=./data/state.json
CONFIG_PATH=./config/config.yaml
```

### Using PostgreSQL locally

1. Start a local Postgres instance (e.g. via Docker):

   ```bash
   docker run -d --name pg \
     -e POSTGRES_USER=sorter -e POSTGRES_PASSWORD=sorter \
     -e POSTGRES_DB=gmail_sorter \
     -p 5432:5432 postgres:16-alpine
   ```

2. Set in `.env`:

   ```env
   DATABASE_URL=postgresql://sorter:sorter@localhost:5432/gmail_sorter
   ```

3. Set in `config/config.yaml`:

   ```yaml
   state_backend: "postgres"
   ```

---

## Project Structure

```
gmail-sorter/
├── src/
│   ├── __init__.py              # Package init
│   ├── main.py                  # Entry point, orchestration, CLI
│   ├── auth.py                  # Google OAuth2 flow and token management
│   ├── gmail_client.py          # Gmail API wrapper (history, labels, watch)
│   ├── pubsub_client.py         # Cloud Pub/Sub pull subscriber
│   ├── classifier.py            # AI email classifier (Copilot + OpenAI backends)
│   ├── config_loader.py         # YAML config loading and validation
│   ├── label_manager.py         # Gmail label cache and creation
│   └── state_manager/           # Pluggable state persistence
│       ├── __init__.py          # create_state_manager() factory
│       ├── base.py              # BaseStateManager abstract class
│       ├── json_backend.py      # Atomic JSON file (default)
│       ├── sqlite_backend.py    # Local SQLite database
│       └── postgres_backend.py  # PostgreSQL database
├── config/
│   └── config.yaml              # Your categories and settings
├── credentials/
│   └── credentials.json         # OAuth2 client secrets (gitignored)
├── data/                        # Runtime state (gitignored, mounted as volume)
│   ├── token.json               # OAuth2 access + refresh tokens
│   └── state.json               # Gmail history ID + watch expiry (json backend)
├── scripts/
│   └── setup_gcp.sh             # Automated GCP setup script
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
├── .gitignore
├── CHANGELOG.md
└── README.md
```

---

## Troubleshooting

### "No stored history ID found" on every startup

The `data/` directory is not persisted.  Ensure the Docker volume is mounted
correctly and that `docker-compose down` (without `-v`) was used to stop the
container.

### "historyId is too old" warning

If the agent was stopped for more than 30 days the Gmail history cursor
expires.  The agent resets automatically by using the current `historyId`
from your profile — emails received during the downtime are skipped.

### OAuth consent screen warning

If you see "This app isn't verified" when authorizing, click
**Advanced → Go to (unsafe)**.  This is expected for personal OAuth2 apps
that have not been through Google's verification process.

### "403 Forbidden: Request had insufficient authentication scopes"

Delete `data/token.json` and re-run `--setup`.  The stored token may have
been issued with insufficient scopes.

### Rate limiting (HTTP 429)

The Gmail API has per-user quotas.  The agent retries with exponential
backoff automatically.  If you process many emails in a burst, consider
lowering `max_emails_per_poll` in the config.

### Classification always returns `None`

Enable `log_level: "DEBUG"` and check the raw AI response in the logs.
Common causes: the categories list is empty, descriptions are too vague, or
the `GITHUB_TOKEN` does not have an active Copilot subscription attached.
If using `ai_provider: openai`, verify `OPENAI_API_KEY` is valid.

### "psycopg2 is required" error

You have `state_backend: "postgres"` set but `psycopg2-binary` is not
installed.  It is included in `requirements.txt`; rebuild the Docker image:

```bash
docker-compose build --no-cache sorter
```

---

## Security Notes

- **credentials.json** and **token.json** must never be committed to git.
  They are in `.gitignore`.
- **GITHUB_TOKEN** (or `OPENAI_API_KEY`) must never be committed to git.
  Store it only in your `.env` file, which is also in `.gitignore`.
- The Docker container runs as a non-root user (`uid=1000`).
- The credentials directory is mounted read-only inside the container.
- No inbound network ports are opened; the agent only makes outbound
  connections to the Gmail API, Pub/Sub, and the configured AI provider.
