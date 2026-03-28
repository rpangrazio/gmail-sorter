#!/usr/bin/env bash
# =============================================================================
# Gmail AI Sorter — GCP Setup Script
# =============================================================================
#
# Automates the Google Cloud setup steps described in README.md:
#   1. Enables required APIs.
#   2. Creates a Pub/Sub topic and pull subscription.
#   3. Grants Gmail's push service account publish permission on the topic.
#
# Usage:
#   chmod +x scripts/setup_gcp.sh
#   GCP_PROJECT=my-project-id ./scripts/setup_gcp.sh
#
# Prerequisites:
#   - gcloud CLI installed and authenticated (`gcloud auth login`)
#   - Project billing enabled
# =============================================================================

set -euo pipefail

# ---------------------------------------------------------------------------
# Configuration — override via environment variables
# ---------------------------------------------------------------------------
GCP_PROJECT="${GCP_PROJECT:?ERROR: GCP_PROJECT environment variable is required.}"
TOPIC_NAME="${TOPIC_NAME:-gmail-sorter}"
SUBSCRIPTION_NAME="${SUBSCRIPTION_NAME:-gmail-sorter-sub}"
REGION="${REGION:-us-central1}"

# Gmail's push notification service account (fixed by Google).
GMAIL_PUSH_SA="gmail-api-push@system.gserviceaccount.com"

echo "============================================================"
echo "Gmail AI Sorter — GCP Setup"
echo "Project:      $GCP_PROJECT"
echo "Topic:        $TOPIC_NAME"
echo "Subscription: $SUBSCRIPTION_NAME"
echo "============================================================"
echo ""

# ---------------------------------------------------------------------------
# Step 1: Set active project
# ---------------------------------------------------------------------------
echo "[1/5] Setting active GCP project..."
gcloud config set project "$GCP_PROJECT"

# ---------------------------------------------------------------------------
# Step 2: Enable required APIs
# ---------------------------------------------------------------------------
echo "[2/5] Enabling required APIs..."
gcloud services enable \
    gmail.googleapis.com \
    pubsub.googleapis.com \
    --project="$GCP_PROJECT"
echo "      APIs enabled."

# ---------------------------------------------------------------------------
# Step 3: Create Pub/Sub topic
# ---------------------------------------------------------------------------
TOPIC_PATH="projects/${GCP_PROJECT}/topics/${TOPIC_NAME}"
echo "[3/5] Creating Pub/Sub topic: $TOPIC_PATH ..."
if gcloud pubsub topics describe "$TOPIC_NAME" --project="$GCP_PROJECT" &>/dev/null; then
    echo "      Topic already exists — skipping creation."
else
    gcloud pubsub topics create "$TOPIC_NAME" --project="$GCP_PROJECT"
    echo "      Topic created."
fi

# ---------------------------------------------------------------------------
# Step 4: Create pull subscription
# ---------------------------------------------------------------------------
echo "[4/5] Creating Pub/Sub pull subscription: $SUBSCRIPTION_NAME ..."
if gcloud pubsub subscriptions describe "$SUBSCRIPTION_NAME" --project="$GCP_PROJECT" &>/dev/null; then
    echo "      Subscription already exists — skipping creation."
else
    gcloud pubsub subscriptions create "$SUBSCRIPTION_NAME" \
        --topic="$TOPIC_NAME" \
        --project="$GCP_PROJECT" \
        --ack-deadline=60 \
        --message-retention-duration=7d \
        --expiration-period=never
    echo "      Subscription created."
fi

# ---------------------------------------------------------------------------
# Step 5: Grant Gmail push SA publish permission on the topic
# ---------------------------------------------------------------------------
echo "[5/5] Granting Gmail push service account publish permission..."
gcloud pubsub topics add-iam-policy-binding "$TOPIC_NAME" \
    --project="$GCP_PROJECT" \
    --member="serviceAccount:${GMAIL_PUSH_SA}" \
    --role="roles/pubsub.publisher" \
    --quiet
echo "      IAM policy binding added."

# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------
echo ""
echo "============================================================"
echo "GCP setup complete!"
echo ""
echo "Next steps:"
echo "  1. Create OAuth2 credentials in Google Cloud Console:"
echo "     https://console.cloud.google.com/apis/credentials?project=$GCP_PROJECT"
echo "     → Create Credentials → OAuth 2.0 Client ID → Desktop App"
echo "     → Download JSON → save to ./credentials/credentials.json"
echo ""
echo "  2. Update config/config.yaml with:"
echo "     google_project_id: \"$GCP_PROJECT\""
echo "     pubsub_subscription: \"projects/$GCP_PROJECT/subscriptions/$SUBSCRIPTION_NAME\""
echo "     gmail_watch_topic: \"projects/$GCP_PROJECT/topics/$TOPIC_NAME\""
echo ""
echo "  3. Copy .env.example to .env and set ANTHROPIC_API_KEY."
echo ""
echo "  4. Run OAuth2 setup:"
echo "     docker-compose run --rm sorter python -m src.main --setup"
echo ""
echo "  5. Start the agent:"
echo "     docker-compose up -d"
echo "============================================================"
