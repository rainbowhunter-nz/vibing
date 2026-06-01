# vibing_host_runtime

Host worker. Runs on host machine, controls Dev Container CLI.

## Files

- `cli.py`: `vibing host-runtime ...`.
- `client.py`: worker config/default URLs.
- `devcontainer_cli.py`: Dev Container CLI subprocess adapter.
- `agent_launcher.py`: starts `vibing devcontainer-runtime ...` inside container.
- `command_handler.py`: maps lifecycle commands to CLI calls and runtime events.
- `runtime.py`: simple runtime protocol/worker shell.

## Context

- Connects to API `/runtime/ws` as `host_runtime_worker`.
- Emits lifecycle runtime events through `vibing_runtime_client`.
- Tests: `tests/host_runtime`.
