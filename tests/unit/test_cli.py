"""Unit tests for CLI command wiring and global options."""

from __future__ import annotations

from types import SimpleNamespace

from click.testing import CliRunner

from gmail_sorter.cli import main


def _fake_config() -> SimpleNamespace:
    """Return a lightweight config object used by CLI tests."""

    return SimpleNamespace(
        processing=SimpleNamespace(dry_run=False),
        logging=SimpleNamespace(level="INFO"),
    )


def test_validate_config_with_valid_config_exits_zero(monkeypatch) -> None:
    """`validate-config` succeeds when configuration loads cleanly."""

    monkeypatch.setattr("gmail_sorter.cli.load_config", lambda _path: _fake_config())
    runner = CliRunner()

    result = runner.invoke(main, ["validate-config"])

    assert result.exit_code == 0
    assert "Configuration is valid." in result.output


def test_validate_config_with_invalid_config_exits_one(monkeypatch) -> None:
    """`validate-config` exits non-zero when config validation fails."""

    def _raise(_path):
        raise SystemExit(1)

    monkeypatch.setattr("gmail_sorter.cli.load_config", _raise)
    runner = CliRunner()

    result = runner.invoke(main, ["validate-config"])

    assert result.exit_code == 1


def test_version_flag_prints_project_version() -> None:
    """`--version` reports the CLI package version."""

    runner = CliRunner()
    result = runner.invoke(main, ["--version"])

    assert result.exit_code == 0
    assert "1.0.0" in result.output
