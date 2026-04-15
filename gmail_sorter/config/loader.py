"""Configuration file loading helpers."""

from __future__ import annotations

import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

from gmail_sorter.config.models import AppConfig


def load_config(path: str | Path) -> AppConfig:
    """Load, validate, and return application configuration.

    Args:
        path: Path to the YAML configuration file.

    Returns:
        A validated ``AppConfig`` instance.

    Raises:
        SystemExit: If the configuration file cannot be parsed or validated.
    """

    config_path = Path(path)
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            data = yaml.safe_load(handle)
    except yaml.YAMLError as error:
        print(f"Configuration YAML parse error: {error}", file=sys.stderr)
        raise SystemExit(1) from error

    try:
        return AppConfig.model_validate(data)
    except ValidationError as error:
        for item in error.errors():
            location = ".".join(str(part) for part in item.get("loc", ()))
            message = item.get("msg", "Unknown validation error")
            print(f"{location}: {message}", file=sys.stderr)
        raise SystemExit(1) from error
