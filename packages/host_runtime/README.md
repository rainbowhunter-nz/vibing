# vibing-host-runtime

Host-side runtime skeleton for the Vibing MVP.

The Host Runtime Worker owns devcontainer-lifecycle operations (eventually:
Dev Container CLI, Docker/Podman). This package currently ships a skeleton
`HostRuntime` implementation with no runtime infra — see ADR-0003 for the host-vs-devcontainer responsibility split.
