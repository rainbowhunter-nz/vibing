# Runtimes connect to the Control Plane over TCP/IP in a star topology

The Control Plane (backend) is the single hub. Runtimes (Host Runtime Worker, Devcontainer Runtime Agent) are out-of-process and connect to it over TCP/IP: the Control Plane sends Commands and consumes the Runtime Events they emit. There is **no runtime-to-runtime communication** — every Command and Event flows through the hub. The frontend is a separate client of the same hub over the existing `/api/v1` HTTP API; it is not part of the Control Plane.

This rules out the in-process, synchronous `handle(command) -> list[RuntimeEvent]` signature the current skeletons carry: a Host Runtime Worker must run on the host to drive containers, and a devcontainer boot emits events over time (`starting`, then later `running`/`failed`), so events are an async stream, not a return value. The skeleton signature is a placeholder, not the committed contract.

The MVP runtime channel is a single WebSocket connection initiated by each Runtime to the Control Plane. The Control Plane sends Commands over that connection, and the Runtime sends Runtime Events back over the same connection. We chose WebSocket over HTTP callbacks because the Host Runtime Worker should not need to expose its own callback server, and over a raw socket because WebSocket gives us a standard local TCP/IP stream without inventing framing.

For MVP, the Host Runtime Worker is a separately-started process, not a child process supervised by the Control Plane. That keeps the Control Plane out of host process management while the runtime protocol and lifecycle behavior are still being proven; a wrapper script or desktop shell can later start both processes without changing the runtime boundary.

The MVP supports one connected Host Runtime Worker per Control Plane. Accepting multiple host workers would require stable runtime identity and explicit Devcontainer-to-runtime ownership so Commands are routed to the right host process; that routing model is unnecessary while Vibing is local-only, single-user, and single-host.

The Host Runtime Worker MVP supports `start_devcontainer` and `stop_devcontainer`; `restart_devcontainer` is not a protocol Command. Restart is a convenience workflow composed from stop then start, which keeps the Command vocabulary smaller and avoids defining separate restart failure semantics.

The Host Runtime Worker shells out to the official `devcontainer` CLI for Devcontainer lifecycle operations. Python Docker/Podman socket libraries manage raw containers, not Devcontainer semantics such as `devcontainer.json`, features, lifecycle commands, workspace rules, and remote user behavior; using them directly would mean reimplementing part of the Dev Containers spec.

Status: accepted
