# vibing-workspace-runtime

Workspace-side runtime skeleton for the Vibing MVP.

The Workspace Runtime Agent owns Claude-session lifecycle inside a workspace
(eventually: launching Claude Code, PTY, streaming output, approval
detection). This package currently ships a no-op `WorkspaceRuntime`
implementation — see `docs/runtime-boundaries.md` at the repo root for the
host-vs-workspace responsibility split.
