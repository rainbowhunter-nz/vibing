## Environment

You are running in a devcontainer. The devcontainer is configured to be docker-outside-of-docker — the host's container engine socket is mounted in, so `docker` commands here drive containers on the host, not inside this container.

Containers started by the stack are published on the host. To reach them from inside this devcontainer, use `host.docker.internal` (not `localhost`).

This project uses `uv` for managing python package. Please avoid modifing `pyproject.toml`. Use `uv` instead. load the `uv` skill for detail usage.