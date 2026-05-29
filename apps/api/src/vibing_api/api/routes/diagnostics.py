"""Local diagnostics for Vibing prerequisites."""

from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel

from vibing_api.core.database import get_connection
from vibing_api.core.schema import read_schema_version

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
            version = read_schema_version(conn)
    except Exception as exc:
        return DiagnosticCheck(id="sqlite", label="SQLite", status="fail", message=str(exc))
    if version is None:
        return DiagnosticCheck(
            id="sqlite",
            label="SQLite",
            status="fail",
            message="schema_version missing from app_meta",
        )
    return DiagnosticCheck(
        id="sqlite", label="SQLite", status="ok", message=f"schema_version={version}"
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
