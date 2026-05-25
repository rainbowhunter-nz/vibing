import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from vibing_api.core.config import settings

_SQLITE_PREFIX = "sqlite:///"


def _database_path() -> Path:
    url = settings.database_url
    if not url.startswith(_SQLITE_PREFIX):
        raise ValueError(f"Only sqlite:/// URLs are supported, got: {url!r}")
    return Path(url[len(_SQLITE_PREFIX) :])


def init_db() -> None:
    """Create the SQLite database file and apply minimal schema bootstrap."""
    path = _database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS app_meta ("
            "  key TEXT PRIMARY KEY,"
            "  value TEXT NOT NULL"
            ")"
        )
        conn.execute(
            "INSERT OR IGNORE INTO app_meta (key, value) VALUES ('schema_version', '1')"
        )
        conn.commit()


@contextmanager
def get_connection() -> Iterator[sqlite3.Connection]:
    conn = sqlite3.connect(_database_path())
    try:
        yield conn
    finally:
        conn.close()
