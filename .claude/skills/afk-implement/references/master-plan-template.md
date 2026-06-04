# Master Plan (`.afk/afk-plan.md`)

Run's durable state — written once by the supervisor, updated by each runner. Recovery anchor: a fresh agent rebuilds the whole run from this + Jira + git, nothing in memory. Keep greppable; the driver loops while `^Run state: running` matches.

## Template

```markdown
# AFK Run: <project / filter>

Run state: running          # running | complete | halted
Branch: wip
Started: <date>

## Project commands
- build: <cmd>
- test: <cmd>
- lint: <cmd>

## Jira workflow map
- ready: <To Do>
- in-progress: <In Progress>
- review: <In Review>

## Batch (execution order)
| # | Ticket | Title | Blocked by | Status |
|---|--------|-------|------------|--------|
| 1 | PROJ-1 | <title> | —      | done        |
| 2 | PROJ-2 | <title> | PROJ-1 | in-progress |
| 3 | PROJ-3 | <title> | —      | pending     |

Status: pending | in-progress | done | blocked.
Per-ticket detail + logs in `.afk/plans/<ticket>-<title>.md`.

## Excluded
- PROJ-9 — blocked by PROJ-8 (not in batch, unsatisfiable)

## Run log
> <ts> supervisor: batch confirmed (3 tickets), loop launched
> <ts> PROJ-1 done — committed <sha>, left In Review
> <ts> PROJ-2 in-progress

## Handoff (rewritten each iteration — context for the next runner)
- Last: <ticket> <one-line outcome>
- <cross-ticket gotcha/convention worth not re-deriving, e.g. tests need `make db` first>
- <anything bearing on the next ticket>
- <open risk to watch, if any>
```

## Rules

- **`Run state`** = loop kill switch. `running` keeps the driver going; `complete` (nothing left) + `halted` (global blocker) stop it. Exactly one value, prefix `Run state: ` (the driver greps it).
- **Status column** = per-ticket recovery truth. `in-progress` before starting; `done` only after committed on `wip` + left In Review. A row stuck `in-progress` after a crash = "reset + redo."
- **Run log** append-only: one line per ticket start/finish/block + final summary. Reconstruct the run from this alone.
- **Handoff** = lean rolling note, **overwritten** (not appended) each iteration. ≤5 bullets: what just finished, cross-ticket gotchas/conventions, anything bearing on the next ticket, open risks. Drop stale items. Not a diary — the Run log is the history; handoff is only what saves the next runner work.
- Keep stages/models/verdicts out — those live in the per-ticket plan. This file = run-level index.
