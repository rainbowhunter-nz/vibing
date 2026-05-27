"""Local diagnostics for Vibing prerequisites."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from vibing_api.core.database import get_connection

router = APIRouter(tags=["diagnostics"])

DiagnosticStatus = Literal["ok", "fail", "unknown"]


class DiagnosticCheck(BaseModel):
    id: str
    label: str
    status: DiagnosticStatus
    message: str | None = None


class DiagnosticsResponse(BaseModel):
    checks: list[DiagnosticCheck]


def _check_backend() -> DiagnosticCheck:
    return DiagnosticCheck(id="backend", label="Backend", status="ok", message="API responding")


def _check_sqlite() -> DiagnosticCheck:
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = 'schema_version'"
            ).fetchone()
    except Exception as exc:
        return DiagnosticCheck(id="sqlite", label="SQLite", status="fail", message=str(exc))
    if row is None:
        return DiagnosticCheck(
            id="sqlite",
            label="SQLite",
            status="fail",
            message="schema_version missing from app_meta",
        )
    return DiagnosticCheck(
        id="sqlite", label="SQLite", status="ok", message=f"schema_version={row[0]}"
    )


_PLACEHOLDER_CHECKS: tuple[tuple[str, str], ...] = (
    ("devcontainer_cli", "Dev Container CLI"),
    ("docker", "Docker"),
    ("podman", "Podman"),
    ("claude_code", "Claude Code"),
)


def _placeholder_checks() -> list[DiagnosticCheck]:
    return [
        DiagnosticCheck(id=cid, label=label, status="unknown", message="Not implemented yet")
        for cid, label in _PLACEHOLDER_CHECKS
    ]


@router.get("/diagnostics", response_model=DiagnosticsResponse)
def get_diagnostics() -> DiagnosticsResponse:
    return DiagnosticsResponse(
        checks=[_check_backend(), _check_sqlite(), *_placeholder_checks()]
    )
