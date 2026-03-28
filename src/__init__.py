"""
Gmail AI Sorter — Intelligently categorizes Gmail using Claude AI.

This package connects to a Gmail account via OAuth2, listens for new emails
through Google Cloud Pub/Sub (triggered by Gmail's watch API), classifies each
email with Claude AI using user-defined categories, and applies Gmail labels.
"""
