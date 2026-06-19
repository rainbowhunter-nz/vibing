# Drop the Agent Session model; the Devcontainer Runtime is a harness-friction companion

ADR-0011 kept two coexisting models in one process: the top-down **Agent Session** (the Control
Plane sends `start_agent_session`, the runtime runs `claude -p`, streams live turn-deltas and serves
transcripts back) and the inside-out **delegation** model (a human drives Claude Code *directly*
inside the container and delegates sub-tasks to other harnesses through a runtime-hosted MCP server).
The two were kept side by side "while the delegation workflow proves itself."

It has proven itself, and the Agent Session model is the wrong shape: driving a coding agent
through a remote control plane is strictly worse than the human using Claude Code directly inside the
container, where they get the harness's own interactive UX. **We drop the Agent Session model
entirely** and keep only delegation.

This deletes a large subsystem. Control Plane: the `agent_sessions` table, the live turn-delta SSE
stream, transcript request/reply, the chat UI, Session Summaries, and the
start/stop/resume/send-input commands. Devcontainer Runtime: the Claude runner, stream normalizer,
transcript parser, content-block decoder, and running-session tracking. (Inbox, Approvals, and
Interventions were already removed.)

The **Devcontainer Runtime** is re-framed accordingly: not a half-owner of agent sessions, but the
**in-container companion that reduces the friction of using Coding Harnesses and adds capability on
top of them.** Today that is (1) harness management — check/install/authenticate managed harnesses
from credentials the Control Plane delivers (ADR-0012), reporting Harness Status up — and (2) the MCP
delegation server (ADR-0011's surviving half). It is explicitly designed to grow more capabilities
(e.g. skills management). The name drops "Agent": the Coding Harness is the agent, and one process
called both was confusing.

Delegated Runs stay **in-container only** — observable by the main harness through MCP
(`get_status`/`get_result`); the Control Plane does not track them. Web observability of delegated
runs is deferred until there is a felt need.

Naming consequences: "Agent Session," "Host Runtime Worker," and the umbrella "Runtime" term are
retired; "Devcontainer Runtime Agent" becomes "Devcontainer Runtime." The runtime channel narrows to
`register`, `command` (`authenticate_harness` today), and `harness_status`.

Supersedes: ADR-0008, ADR-0009, ADR-0010. Re-scopes: ADR-0011 (drops its Agent Session half),
ADR-0013 (Delegated Runs are in-container only, no longer reported as Runtime Events).

Status: accepted
