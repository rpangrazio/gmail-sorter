"""
State manager package for Gmail AI Sorter.

Provides three interchangeable storage backends for persisting the Gmail
history cursor and watch expiry:

* **json** — atomic JSON file write (default, no extra dependencies).
* **sqlite** — local SQLite database (stdlib ``sqlite3``, no extra dependencies).
* **postgres** — PostgreSQL database (requires ``psycopg2-binary``).

Use :func:`create_state_manager` to instantiate the correct backend based on
the ``state_backend`` value from the application configuration.

Example::

    from src.state_manager import create_state_manager

    state = create_state_manager("sqlite", db_path="/data/state.db")
    state.set_history_id("123456")
"""

from .base import BaseStateManager
from .json_backend import JsonStateManager
from .sqlite_backend import SqliteStateManager

# PostgresStateManager is imported lazily inside create_state_manager so that
# the psycopg2 dependency is only required when the postgres backend is actually
# used.  Importing it at module level would cause an ImportError for users who
# have not installed psycopg2-binary.

__all__ = [
    "BaseStateManager",
    "JsonStateManager",
    "SqliteStateManager",
    "PostgresStateManager",
    "create_state_manager",
]


def create_state_manager(backend: str, **kwargs) -> BaseStateManager:
    """
    Factory that returns the appropriate :class:`BaseStateManager` subclass.

    Args:
        backend: Storage backend to use — one of ``"json"``, ``"sqlite"``,
            or ``"postgres"``.
        **kwargs: Backend-specific keyword arguments:

            * ``json`` → ``state_file_path`` *(str)*
            * ``sqlite`` → ``db_path`` *(str)*
            * ``postgres`` → ``dsn`` *(str)* — libpq DSN or
              ``postgresql://`` URL

    Returns:
        A fully initialised :class:`BaseStateManager` instance.

    Raises:
        ValueError: If *backend* is not one of the recognised values.
        KeyError: If a required keyword argument for the chosen backend is
            missing.
        ImportError: If ``backend="postgres"`` and ``psycopg2`` is not installed.
    """
    if backend == "json":
        return JsonStateManager(state_file_path=kwargs["state_file_path"])
    if backend == "sqlite":
        return SqliteStateManager(db_path=kwargs["db_path"])
    if backend == "postgres":
        from .postgres_backend import PostgresStateManager  # lazy import
        return PostgresStateManager(dsn=kwargs["dsn"])
    raise ValueError(
        f"Unknown state_backend {backend!r}. "
        "Valid options are: 'json', 'sqlite', 'postgres'."
    )


# Allow `from src.state_manager import PostgresStateManager` without breaking
# at import time when psycopg2 is absent.
def __getattr__(name: str):
    if name == "PostgresStateManager":
        from .postgres_backend import PostgresStateManager
        return PostgresStateManager
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
