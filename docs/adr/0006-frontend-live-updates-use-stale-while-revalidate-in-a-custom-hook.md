# Frontend live updates use stale-while-revalidate in a custom hook, not a query-cache library

The SPA already receives live invalidations: the Control Plane broadcasts after projection commit ([ADR-0005](0005-frontend-live-updates-use-sse-invalidation-events.md)), the SSE endpoint and the frontend coordinator are in place, and routes wire `register(scope, refetch)`. The only defect was a page flash: `useApiQuery.refetch()` reset query state to `loading`, so the route-level loading UI replaced already-visible data on every invalidation-driven refetch.

We fix this by making the existing `useApiQuery` stale-while-revalidate rather than adopting TanStack Query or hand-rolling a shared cache layer:

- A **same-query refetch** (SSE invalidation or post-action) keeps the current data visible and exposes an `isFetching` flag; it never drops back to `loading`.
- A **deps change** (a different resource, e.g. navigating between Devcontainer detail ids) still shows `loading` — the previous record's data would be wrong, not merely stale.
- An **error during a background refetch** keeps the last-good data with a non-blocking hint; the full `error` state is shown only on first load.
- Invalidations route by `scope` only; the `ids` field stays in the wire contract but is not yet used for filtering.
- On SSE **reconnect** the coordinator re-invokes every registered callback to refetch active queries; there is no `Last-Event-ID` replay.

We considered TanStack Query and a bespoke shared cache. Their headline advantage — a single keyed cache that dedupes queries across components — buys nothing here: every fetch site is per-component and no two simultaneously-mounted components fetch the same query (list uses the collection endpoint, detail uses the single-item endpoint on a separate route, rails fetch health/config). Adopting either would mean a new dependency or bespoke machinery plus a rewrite of every route's fetching, to solve a one-file regression, against the project's "simplicity first" rule. The trade-off we accept: no request dedup and no optimistic mutations out of the box — both negligible for a single-user, local-first MVP with low-volume Runtime Events, and both addable later without redesign.

Status: accepted
