# vibing sandbox

Throwaway project for firing up a devcontainer through the host runtime and
verifying the devcontainer runtime agent end-to-end (no UI required).

Edit / add files here freely — this is the workspace an agent session operates on.

## Devcontainer contract

Vibing injects the Devcontainer Runtime Agent at launch (`docker cp` of `uv` +
the `vibing` wheel from the Control Plane image, then `uv tool install`). Your
project image does **not** need `vibing`, `uv`, or any Vibing-specific packages.

A devcontainer Vibing can drive must provide:

| Requirement | Why |
| --- | --- |
| `claude` on `PATH`, authenticated | Agent sessions invoke Claude Code (`claude -p …`). |
| Network egress | Runtime injection resolves deps from PyPI/CDN; the agent calls the Anthropic API. |
| Linux: `--add-host=host.docker.internal:host-gateway` in `runArgs` | Agent WebSocket reaches the Control Plane on the host. See [`docs/deployment.md`](../../docs/deployment.md). |

This example Dockerfile installs only `claude-code`. `devcontainer.json` carries
the host-gateway `runArgs` entry and passes `ANTHROPIC_API_KEY` from the host.

See [ADR-0004 amendment](../../docs/adr/0004-devcontainer-runtime-agents-connect-on-a-dedicated-endpoint-routed-by-devcontainer-id.md) for the injection model.
