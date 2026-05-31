# vibing-runtime-client

Shared runtime-channel WebSocket client for Vibing runtimes.

`RuntimeChannelClient` handles: connect, bounded exponential-backoff reconnect loop, sending a
register envelope, parsing inbound `command` envelopes, and an `emit(RuntimeEvent)` closure.
Both the Host Runtime Worker and the Devcontainer Runtime Agent use this package.
