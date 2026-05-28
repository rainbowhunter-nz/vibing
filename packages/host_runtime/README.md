# vibing-host-runtime

Host-side runtime skeleton for the Vibing MVP.

The Host Runtime Worker owns workspace-lifecycle operations (eventually:
Dev Container CLI, Docker/Podman). This package currently ships a skeleton
`HostRuntime` implementation with no runtime infra — see
`docs/runtime-boundaries.md` at the repo root for the host-vs-workspace
responsibility split.
