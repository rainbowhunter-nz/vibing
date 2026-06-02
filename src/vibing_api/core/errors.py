"""Standard error response shape and FastAPI handlers."""

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

VALIDATION_ERROR = "VALIDATION_ERROR"
DEVCONTAINER_NOT_FOUND = "DEVCONTAINER_NOT_FOUND"
INVALID_DEVCONTAINER_STATE = "INVALID_DEVCONTAINER_STATE"
RUNTIME_UNAVAILABLE = "RUNTIME_UNAVAILABLE"
AGENT_SESSION_ACTIVE = "AGENT_SESSION_ACTIVE"
AGENT_SESSION_NOT_FOUND = "AGENT_SESSION_NOT_FOUND"
AGENT_SESSION_NOT_ACTIVE = "AGENT_SESSION_NOT_ACTIVE"
INBOX_EVENT_NOT_FOUND = "INBOX_EVENT_NOT_FOUND"
APPROVAL_REQUEST_NOT_FOUND = "APPROVAL_REQUEST_NOT_FOUND"
INTERNAL_SERVER_ERROR = "INTERNAL_SERVER_ERROR"


class APIError(Exception):
    """Base class for API errors that produce the standard error envelope."""

    status_code: int = 500
    code: str = INTERNAL_SERVER_ERROR

    def __init__(self, message: str, details: Any | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details


class DevcontainerNotFoundError(APIError):
    status_code = 404
    code = DEVCONTAINER_NOT_FOUND

    def __init__(self, devcontainer_id: str) -> None:
        super().__init__(f"Devcontainer not found: {devcontainer_id}")


class InvalidDevcontainerStateError(APIError):
    status_code = 409
    code = INVALID_DEVCONTAINER_STATE

    def __init__(self, action: str, current: str, allowed: frozenset[str]) -> None:
        super().__init__(
            f"Cannot {action} devcontainer in status {current!r}; allowed from: {sorted(allowed)}"
        )


class RuntimeUnavailableError(APIError):
    status_code = 409
    code = RUNTIME_UNAVAILABLE

    def __init__(self, message: str = "No Host Runtime Worker is connected") -> None:
        super().__init__(message)


class ActiveAgentSessionError(APIError):
    status_code = 409
    code = AGENT_SESSION_ACTIVE

    def __init__(self, devcontainer_id: str) -> None:
        super().__init__(f"An agent session is already active for devcontainer: {devcontainer_id}")


class AgentSessionNotFoundError(APIError):
    status_code = 404
    code = AGENT_SESSION_NOT_FOUND

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Agent session not found: {session_id}")


class InactiveAgentSessionError(APIError):
    status_code = 409
    code = AGENT_SESSION_NOT_ACTIVE

    def __init__(self, session_id: str) -> None:
        super().__init__(f"Agent session is not active: {session_id}")


class InboxEventNotFoundError(APIError):
    status_code = 404
    code = INBOX_EVENT_NOT_FOUND

    def __init__(self, inbox_event_id: str) -> None:
        super().__init__(f"Inbox event not found: {inbox_event_id}")


class ApprovalRequestNotFoundError(APIError):
    status_code = 404
    code = APPROVAL_REQUEST_NOT_FOUND

    def __init__(self, approval_request_id: str) -> None:
        super().__init__(f"Approval request not found: {approval_request_id}")


def _envelope(code: str, message: str, details: Any | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(APIError)
    async def handle_api_error(_request: Request, exc: APIError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(exc.code, exc.message, exc.details),
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(
        _request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = []
        for err in exc.errors():
            err = dict(err)
            if "ctx" in err:
                err["ctx"] = {k: str(v) for k, v in err["ctx"].items()}
            errors.append(err)
        return JSONResponse(
            status_code=422,
            content=_envelope(
                VALIDATION_ERROR,
                "Request validation failed",
                details=errors,
            ),
        )

    @app.exception_handler(StarletteHTTPException)
    async def handle_http_exception(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Map remaining HTTP errors into the standard envelope. 404s on unknown
        # routes etc. should still look like the rest of the API.
        code = INTERNAL_SERVER_ERROR if exc.status_code >= 500 else "HTTP_ERROR"
        return JSONResponse(
            status_code=exc.status_code,
            content=_envelope(code, str(exc.detail)),
        )
