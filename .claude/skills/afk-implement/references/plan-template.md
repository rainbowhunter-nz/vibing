# Plan Template and Writing Guide

One plan file per ticket at `.afk/plans/<ticket>-<title>.md` (kebab-case the title,
e.g. `PROJ-123-add-login-rate-limit.md`). The ticket-runner writes it before
implementing and **appends to the Log section** as the cycle progresses — it is the
ticket's audit trail. (Run-level state — the batch, order, and `Run state` — lives in
the master plan `.afk/afk-plan.md`, not here.)

## Template

```markdown
# <TICKET-ID>: <Title>

## Ticket summary
<Goal in 1-3 sentences. The acceptance criteria, listed.>

## Context
- Epic: <key/title or n/a>
- Blocked by: <ticket: status, ... — confirm each is satisfied>
- Relevant files/areas: <paths, modules>
- Notes/links: <decisions from linked tickets, docs>

## Decisions
- Review depth: <code-only | code+spec> — <why>
- Out of scope: <what you are deliberately not doing>

## Implementation stages
1. <stage> — files: <...>, model: <haiku|sonnet|opus> — <why this model>
2. <stage> — files: <...>, model: <...>
   (Stages run sequentially, one implementer each.)

## Review criteria
- Spec (if two-pass): <the acceptance criteria to verify>
- Code: <standards, risks, edge cases the reviewer should focus on>

## Log
> <timestamp> <event>   e.g. dispatched stage 1 (sonnet)
> <timestamp> implementer DONE — 3 files, tests pass
> <timestamp> spec review APPROVE
> <timestamp> code review REQUEST_CHANGES — <gist>
> <timestamp> fix cycle 1 dispatched
> <timestamp> code review APPROVE
> <timestamp> committed <sha> on wip; ticket left In Review
```

## Writing guide

Keep the plan tight — it is a working tool, not a document. A senior engineer should
skim it and know exactly what is being built, how, and why.

**Review depth and models** — see the guides in your runner instructions. Both can mix within a
ticket (a `haiku` scaffolding stage feeding an `opus` core-logic stage is fine).

**Breaking into stages.** Stages exist so each implementer gets a focused, well-scoped
task in fresh context. Split at natural seams — scaffolding/types, then core logic,
then wiring/tests — especially when seams warrant different models. Don't over-split:
a small, cohesive ticket is one stage. Stages run sequentially (shared working tree).

**Logging.** Append a line whenever a subagent returns, a verdict lands, a fix cycle
starts, you commit, or you hit a blocker. Future-you (and the human reviewing the run)
reconstruct what happened from this section alone.
