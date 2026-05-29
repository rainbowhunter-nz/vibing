# vibing-protocol

Shared control-plane message shapes for the Vibing MVP runtimes.

This package defines the `Command` and `RuntimeEvent` data models plus their
vocabulary literals (`CommandType`, `EventType`, `RuntimeEventSource`). It has
no behaviour: dispatch, persistence, and transport live in consumers
(`apps/api`, `packages/devcontainer_runtime`).
