# Runtimes connect to the Control Plane over TCP/IP in a star topology

The Control Plane (backend) is the single hub. Runtimes (Host Runtime Worker, Devcontainer Runtime Agent) are out-of-process and connect to it over TCP/IP: the Control Plane sends Commands and consumes the Runtime Events they emit. There is **no runtime-to-runtime communication** — every Command and Event flows through the hub. The frontend is a separate client of the same hub over the existing `/api/v1` HTTP API; it is not part of the Control Plane.

This rules out the in-process, synchronous `handle(command) -> list[RuntimeEvent]` signature the current skeletons carry: a Host Runtime Worker must run on the host to drive containers, and a devcontainer boot emits events over time (`starting`, then later `running`/`failed`), so events are an async stream, not a return value. The skeleton signature is a placeholder, not the committed contract.

Open sub-point: the specific wire protocol for the runtime channel (HTTP callbacks vs. WebSocket vs. raw socket) is not yet decided. The async, streaming nature of events constrains it but does not pick one.

Status: accepted
