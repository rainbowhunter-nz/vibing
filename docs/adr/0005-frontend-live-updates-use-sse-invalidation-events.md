# Frontend live updates use SSE invalidation events

The frontend needs near-immediate Inbox toasts, read-model refreshes, and runtime-connection status updates without turning the browser into another runtime protocol participant. We use one app-level Server-Sent Events stream from the Control Plane to the frontend that sends lightweight invalidation events only; HTTP remains the canonical data and user-action surface, and runtime WebSockets remain reserved for Runtime Commands and Runtime Events. We chose SSE over polling for lower-latency UI updates, and over browser WebSockets because the browser only needs one-way notifications; runtime connection status remains ephemeral manager state and is not persisted in SQLite.

Status: accepted
