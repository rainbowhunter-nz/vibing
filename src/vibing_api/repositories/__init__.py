"""Per-entity repositories wrapping SQL over a sqlite3.Connection.

Convention: repositories EXECUTE but never commit and never raise HTTP
errors — the caller owns the transaction and maps None/False to HTTP.
"""

from vibing_api.repositories.agent_sessions import AgentSession, AgentSessionRepository
from vibing_api.repositories.approvals import ApprovalRepository, ApprovalRequest
from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.inbox import InboxEvent, InboxRepository
from vibing_api.repositories.runtime_events import RuntimeEventRepository
from vibing_api.repositories.summaries import SessionSummary, SessionSummaryRepository

__all__ = [
    "AgentSession",
    "AgentSessionRepository",
    "ApprovalRepository",
    "ApprovalRequest",
    "DevcontainerRepository",
    "InboxEvent",
    "InboxRepository",
    "RuntimeEventRepository",
    "SessionSummary",
    "SessionSummaryRepository",
]
