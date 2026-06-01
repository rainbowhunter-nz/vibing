import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from vibing_api.core.config import settings
from vibing_api.core.schema import apply_schema

_SQLITE_PREFIX = "sqlite:///"


def _database_path() -> Path:
    url = settings.database_url
    if not url.startswith(_SQLITE_PREFIX):
        raise ValueError(f"Only sqlite:/// URLs are supported, got: {url!r}")
    return Path(url[len(_SQLITE_PREFIX) :])


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create the SQLite database file and apply schema. Safe to run repeatedly."""
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _connect(path) as conn:
        apply_schema(conn)
        conn.commit()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = _connect(_database_path())
    try:
        yield conn
    finally:
        conn.close()
