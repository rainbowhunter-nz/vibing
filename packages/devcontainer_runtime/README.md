# vibing-devcontainer-runtime

Devcontainer-side runtime skeleton for the Vibing MVP.

The Devcontainer Runtime Agent owns Claude-session lifecycle inside a devcontainer
(eventually: launching Claude Code, PTY, streaming output, approval
detection). This package currently ships a no-op `DevcontainerRuntime`
implementation — see ADR-0003 for the host-vs-devcontainer responsibility split.
