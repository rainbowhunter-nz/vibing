## Environment

You are running in a devcontainer. The devcontainer is configured to be docker-outside-of-docker — the host's container engine socket is mounted in, so `docker` commands here drive containers on the host, not inside this container.

Containers started by the stack are published on the host. To reach them from inside this devcontainer, use `host.docker.internal` (not `localhost`).

This project uses `uv` for managing python package. Please avoid modifing `pyproject.toml`. Use `uv` instead. load the `uv` skill for detail usage.

When User ask you to work on a jira ticket, Always read and understand the tickt first.

## Simplicity First

Minimum code that solves the problem. Nothing speculative.

- No features beyond what was asked.
- No abstractions unless necessary.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- Prefer self-explanatory code over comment. Only short and concise comment if necessary.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.