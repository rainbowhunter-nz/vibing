from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from vibing_api.core.database import get_connection, init_db
from vibing_api.core.vocabularies import (
    AgentSessionStatus,
    ApprovalStatus,
    DevcontainerStatus,
    InboxEventType,
)
from vibing_api.dev.sample_data import (
    SAMPLE_AGENT_SESSIONS,
    SAMPLE_APPROVAL_REQUESTS,
    SAMPLE_ID_PREFIX,
    SAMPLE_INBOX_EVENTS,
    SAMPLE_DEVCONTAINERS,
    reset,
    seed,
    status,
)


@pytest.fixture
def seeded_db(db_path: Path) -> Path:
    init_db()
    with get_connection() as conn:
        seed(conn)
        conn.commit()
    return db_path


def test_seed_inserts_curated_dataset(seeded_db: Path) -> None:
    expected = {
        "devcontainers": len(SAMPLE_DEVCONTAINERS),
        "agent_sessions": len(SAMPLE_AGENT_SESSIONS),
        "approval_requests": len(SAMPLE_APPROVAL_REQUESTS),
        "inbox_events": len(SAMPLE_INBOX_EVENTS),
    }
    with get_connection() as conn:
        for table, count in expected.items():
            row = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE id LIKE ?",
                (f"{SAMPLE_ID_PREFIX}%",),
            ).fetchone()
            assert row[0] == count, f"{table}: expected {count}, got {row[0]}"


def test_seed_is_idempotent(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        seed(conn)
        conn.commit()
    with get_connection() as conn:
        seed(conn)
        conn.commit()
    with get_connection() as conn:
        total = conn.execute(
            "SELECT COUNT(*) FROM devcontainers WHERE id LIKE ?",
            (f"{SAMPLE_ID_PREFIX}%",),
        ).fetchone()[0]
    assert total == len(SAMPLE_DEVCONTAINERS)


def test_reset_removes_only_sample_rows(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO devcontainers "
            "(id, name, local_path, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                "real-1",
                "real devcontainer",
                "/tmp/real",
                "created",
                "2026-01-01T00:00:00+00:00",
                "2026-01-01T00:00:00+00:00",
            ),
        )
        seed(conn)
        conn.commit()
    with get_connection() as conn:
        removed = reset(conn)
        conn.commit()
    assert removed == 12
    with get_connection() as conn:
        remaining_sample = conn.execute(
            "SELECT COUNT(*) FROM devcontainers WHERE id LIKE ?",
            (f"{SAMPLE_ID_PREFIX}%",),
        ).fetchone()[0]
        real_row = conn.execute(
            "SELECT id, name FROM devcontainers WHERE id = ?",
            ("real-1",),
        ).fetchone()
    assert remaining_sample == 0
    assert real_row is not None
    assert real_row[0] == "real-1"


def test_reset_on_empty_db_is_safe(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        removed = reset(conn)
        conn.commit()
    assert removed == 0


def test_status_counts_sample_rows(db_path: Path) -> None:
    init_db()
    with get_connection() as conn:
        before = status(conn)
        seed(conn)
        conn.commit()
        after = status(conn)
        reset(conn)
        conn.commit()
        after_reset = status(conn)
    assert before == {
        "devcontainers": 0,
        "agent_sessions": 0,
        "approval_requests": 0,
        "inbox_events": 0,
    }
    assert after == {
        "devcontainers": len(SAMPLE_DEVCONTAINERS),
        "agent_sessions": len(SAMPLE_AGENT_SESSIONS),
        "approval_requests": len(SAMPLE_APPROVAL_REQUESTS),
        "inbox_events": len(SAMPLE_INBOX_EVENTS),
    }
    assert after_reset == before


def test_seeded_sample_devcontainers_visible_via_api(client: TestClient) -> None:
    with get_connection() as conn:
        seed(conn)
        conn.commit()
    response = client.get("/api/v1/devcontainers")
    assert response.status_code == 200
    names = sorted(item["name"] for item in response.json()["items"])
    assert names == [
        "[sample] vibing-api",
        "[sample] vibing-cli",
        "[sample] vibing-web",
    ]


def test_sample_rows_use_valid_vocabulary_values() -> None:
    dc_statuses = frozenset(DevcontainerStatus)
    session_statuses = frozenset(AgentSessionStatus)
    approval_statuses = frozenset(ApprovalStatus)
    inbox_event_types = frozenset(InboxEventType)

    for row in SAMPLE_DEVCONTAINERS:
        assert row["status"] in dc_statuses, f"bad devcontainer status: {row['status']}"
    for row in SAMPLE_AGENT_SESSIONS:
        assert row["status"] in session_statuses, f"bad session status: {row['status']}"
    for row in SAMPLE_APPROVAL_REQUESTS:
        assert row["status"] in approval_statuses, f"bad approval status: {row['status']}"
    for row in SAMPLE_INBOX_EVENTS:
        assert row["event_type"] in inbox_event_types, f"bad inbox event_type: {row['event_type']}"
