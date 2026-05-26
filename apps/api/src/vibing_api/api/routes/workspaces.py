import sqlite3
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Response, status

from vibing_api.api.schemas.workspaces import (
    Workspace,
    WorkspaceCreateRequest,
    WorkspaceList,
    WorkspaceUpdateRequest,
)
from vibing_api.core.database import get_connection
from vibing_api.core.errors import WorkspaceNotFoundError

router = APIRouter(tags=["workspaces"], prefix="/workspaces")

_SOURCE_TYPE_LOCAL_FOLDER = "local_folder"
_INITIAL_STATUS = "created"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _row_to_workspace(row: sqlite3.Row) -> Workspace:
    return Workspace(
        id=row["id"],
        name=row["name"],
        local_path=row["source_value"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@router.post("", response_model=Workspace, status_code=status.HTTP_201_CREATED)
def create_workspace(payload: WorkspaceCreateRequest) -> Workspace:
    workspace_id = str(uuid.uuid4())
    now = _now()
    with get_connection() as conn:
        conn.execute(
            "INSERT INTO workspaces "
            "(id, name, source_type, source_value, status, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                workspace_id,
                payload.name,
                _SOURCE_TYPE_LOCAL_FOLDER,
                payload.local_path,
                _INITIAL_STATUS,
                now,
                now,
            ),
        )
        conn.commit()
    return Workspace(
        id=workspace_id,
        name=payload.name,
        local_path=payload.local_path,
        status=_INITIAL_STATUS,
        created_at=now,
        updated_at=now,
    )


@router.get("", response_model=WorkspaceList)
def list_workspaces() -> WorkspaceList:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, source_value, status, created_at, updated_at "
            "FROM workspaces ORDER BY created_at"
        ).fetchall()
    return WorkspaceList(items=[_row_to_workspace(row) for row in rows])


@router.get("/{workspace_id}", response_model=Workspace)
def get_workspace(workspace_id: str) -> Workspace:
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, name, source_value, status, created_at, updated_at "
            "FROM workspaces WHERE id = ?",
            (workspace_id,),
        ).fetchone()
    if row is None:
        raise WorkspaceNotFoundError(workspace_id)
    return _row_to_workspace(row)


@router.patch("/{workspace_id}", response_model=Workspace)
def update_workspace(workspace_id: str, payload: WorkspaceUpdateRequest) -> Workspace:
    updates = payload.model_dump(exclude_none=True)
    with get_connection() as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT id, name, source_value, status, created_at, updated_at "
            "FROM workspaces WHERE id = ?",
            (workspace_id,),
        ).fetchone()
        if row is None:
            raise WorkspaceNotFoundError(workspace_id)
        if not updates:
            return _row_to_workspace(row)
        updated_at = _now()
        set_clause = ", ".join(f"{field} = ?" for field in updates)
        params = (*updates.values(), updated_at, workspace_id)
        conn.execute(
            f"UPDATE workspaces SET {set_clause}, updated_at = ? WHERE id = ?",
            params,
        )
        conn.commit()
        row = conn.execute(
            "SELECT id, name, source_value, status, created_at, updated_at "
            "FROM workspaces WHERE id = ?",
            (workspace_id,),
        ).fetchone()
    return _row_to_workspace(row)


@router.delete("/{workspace_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workspace(workspace_id: str) -> Response:
    with get_connection() as conn:
        cursor = conn.execute("DELETE FROM workspaces WHERE id = ?", (workspace_id,))
        conn.commit()
        if cursor.rowcount == 0:
            raise WorkspaceNotFoundError(workspace_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
