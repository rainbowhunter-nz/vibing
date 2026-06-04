# Control Plane API Mocking uses MSW and a dev EventSource adapter

Frontend UI states should be inspectable without a running Control Plane, including screens that depend on live invalidation events. We use MSW for mock `/api/v1` HTTP responses and a small dev-only `EventSource` adapter for `/api/v1/events`, because request/response mocking and long-lived event delivery have different mechanics. Mock mode starts from an explicit dev command, exposes manual scenario and invalidation controls through dev-only routes, and is a UI inspection aid rather than a Runtime, Control Plane, projection, or workflow simulator.

Status: accepted
