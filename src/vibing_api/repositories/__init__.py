"""Per-entity repositories wrapping SQL over a sqlite3.Connection.

Convention: repositories EXECUTE but never commit and never raise HTTP
errors — the caller owns the transaction and maps None/False to HTTP.
"""

from vibing_api.repositories.devcontainers import DevcontainerRepository
from vibing_api.repositories.harness_credentials import HarnessCredentialRepository

__all__ = [
    "DevcontainerRepository",
    "HarnessCredentialRepository",
]
