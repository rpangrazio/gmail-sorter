"""Command-line interface for gmail-sorter."""

from __future__ import annotations

import click


@click.group()
def main() -> None:
    """Run the gmail-sorter CLI."""


if __name__ == "__main__":
    main()
