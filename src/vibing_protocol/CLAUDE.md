# vibing_protocol

Shared typed contract between API, runtimes, and frontend docs.

## Files

- `messages.py`: WebSocket envelopes — `RegisterEnvelope`, `DelegatedRunsEnvelope`/`DelegatedRunItem`.
- `channel.py`: wire codec — `encode(envelope)`/`decode(raw)` shared by both ends of the runtime channel.

## Context

- The runtime channel is **outbound-only** (Runtime → Control Plane): `register` + `delegated_runs`. No Command direction, no `harness_status` push — harness setup/status is Control-Plane `devcontainer exec` (ADR-0019).
- Both the Control Plane and the Devcontainer Runtime serialize/parse envelopes through `channel.encode`/`channel.decode`.
- Keep dependencies light: Pydantic + stdlib.
