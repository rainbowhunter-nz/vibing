# vibing_runtime_client

Generic WebSocket client for the Control Plane runtime channel (ADR-0003). Connects,
registers, reconnects with bounded backoff. Knows no domain message types beyond Command.

## API

`RuntimeChannelClient(control_plane_url, register, handler)`
- `register`: `RegisterEnvelope` sent on every (re)connect.
- `handler`: `async (command: Command, send) -> None`. Commands run serially, FIFO,
  no replay after disconnect. `send(envelope)` serializes any pydantic envelope to the ws —
  handler picks the envelope type (`RuntimeEventEnvelope`, `TurnDeltaEnvelope`, ...).

`client.on_request(message_type, respond)` — register request/reply responder (ADR-0009).
`respond` gets the raw message dict, returns the reply envelope (echo `request_id` yourself).
Responder failure -> logged, no reply; Control Plane timeout handles it.

`client.run()` — async, run forever until `stop()`. `client.run_blocking()` — sync entry
point, stops cleanly on SIGTERM/SIGINT.

## Example

```python
from vibing_protocol import Command, RegisterEnvelope, RuntimeEvent, RuntimeEventEnvelope
from vibing_runtime_client import RuntimeChannelClient

async def handle(command: Command, send) -> None:
    await send(RuntimeEventEnvelope(event=RuntimeEvent(
        event_type="devcontainer_started",
        source="host_runtime_worker",
        devcontainer_id=command.devcontainer_id,
    )))

client = RuntimeChannelClient(
    "ws://localhost:8000/api/v1/runtime/ws",
    RegisterEnvelope(source="host_runtime_worker"),
    handle,
)
client.run_blocking()
```
