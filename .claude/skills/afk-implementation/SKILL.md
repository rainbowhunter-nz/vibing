---
name: afk-implementation
description: Autonomously implement every `ready-for-agent` Jira ticket under a single epic, one after another, with no human in the loop. Drives a Ralph loop that re-feeds a per-ticket playbook (superpowers brainstorming → plan → TDD → verify) and commits each finished ticket to that epic's branch (`VIB-<n>-<slug>`). Use whenever the user wants to clear an epic's backlog unattended — "AFK", "overnight run", "work through the ready tickets in this epic", "batch-implement the open tickets", "hands-off / unsupervised implementation". Scoped to the vibing (VIB) Jira project.
disable-model-invocation: true
---

# AFK Implementation

Clear one epic's `ready-for-agent` backlog without a human present. You resolve the
target epic, set up its branch, then launch a **Ralph loop** (`/ralph-loop`) whose
prompt points every iteration at the per-ticket playbook. Each iteration implements
exactly one ticket end-to-end, commits it to the epic branch, transitions it in Jira,
and exits — the loop re-feeds the same prompt and the next ticket gets picked up. The
run ends when no ready tickets remain under the epic (success) or a ticket hits an
unrecoverable blocker (stop).

This skill only ever runs when the user explicitly invokes it. It is unsupervised and
will write code, run checks, and move Jira tickets on its own — so the guardrails below
are load-bearing, not decoration.

## Operating decisions (fixed for this project)

These were chosen deliberately — do not "improve" them mid-run:

- **Scope gate:** only To Do tickets carrying the `ready-for-agent` label **and parented
  to the target epic**. The label is the human's opt-in; never touch unlabeled tickets,
  and never stray outside the epic this run targets.
- **One epic per run:** a single AFK run implements exactly one epic's ready tickets. To
  work a second epic, start another run.
- **Dependency-aware order:** tickets are picked in `Blocked by` order, not raw priority — a
  ticket whose blockers aren't yet Done/In Review is skipped until they are.
- **Isolation:** one branch per run, named for the epic (`VIB-<n>-<slug>`). Every ticket
  commits onto it sequentially. No per-ticket branches, no PRs, no pushing.
- **On unrecoverable failure:** stop the entire loop and report. One bad ticket ends the
  session rather than silently churning.
- **Autonomy:** the loop is the user's fully-authorized delegate and never asks the human
  anything. See the playbook's autonomy rules.

## Config and defaults

The skill takes optional arguments; otherwise use these defaults:

| Setting | Default | Notes |
|---|---|---|
| `project` | `VIB` | Jira project key |
| `cloudId` | `70b0455e-11e5-47f8-8c2a-f91ba4065e51` | rainbowhunter Atlassian site |
| `label` | `ready-for-agent` | scope gate |
| `epic` | — | target epic key (e.g. `VIB-5`); if omitted, inferred in pre-flight |
| `branch` | `VIB-<n>-<slug>` | derived from the epic key + slugified summary, e.g. `VIB-5-product-foundation` |

The Jira MCP must be configured. If it is not reachable, STOP and tell the user — do not
start a loop you can't drive.

## Phase 1 — Pre-flight (run once, before the loop)

Do this yourself, in the current turn, before launching anything:

1. **Verify Jira.** Confirm the MCP answers and the project/cloudId resolve. STOP if not.
2. **Resolve the target epic.** A run targets exactly one epic.
   - If the user passed an `epic` (key or name), use it.
   - Otherwise, survey the ready tickets project-wide and group them by parent epic. If
     they all share one epic, that's the target. If they span several, pick the epic with
     the most ready tickets (tie-break: highest-priority then oldest ready ticket), and
     **tell the user which epic you chose and why** before continuing.
   - Fetch the epic and slugify its summary to build the branch name `VIB-<n>-<slug>`
     (lowercase, spaces/underscores → hyphens, drop other punctuation, ~5 words max).
     E.g. `VIB-5` "Product Foundation" → `VIB-5-product-foundation`.
3. **Survey the work.** Query the epic's ready tickets so you know the size of the run:
   ```
   project = <project> AND status = "To Do" AND labels = "<label>"
     AND issuetype != Epic AND parent = <epic>
   ORDER BY priority DESC, created ASC
   ```
   Report the epic, count, and keys to the user. If the count is 0, say so and stop —
   nothing to do.
4. **Clean tree + fresh base.** Ensure `git status` is clean (STOP if dirty — don't
   bury the user's uncommitted work). From an up-to-date `main`, create and check out the
   epic branch: `git checkout -b VIB-<n>-<slug>`. If that branch already exists, STOP and
   surface it — don't clobber prior work.
5. **Size the safety net.** Set `--max-iterations` to `ready_count + 2`. One ticket ≈ one
   iteration; the small buffer absorbs a re-feed without letting a stuck run sprawl (the
   failure path stops the loop anyway).

## Phase 2 — Launch the loop

Invoke the Ralph loop with a short, stable prompt that defers all detail to the playbook
file (this keeps the re-fed prompt small and avoids quoting a huge string):

```
/ralph-loop "AFK implementation run. Config: project=<project>, cloudId=<cloudId>, label=<label>, epic=<epic>, branch=<branch>. Read .claude/skills/afk-implementation/references/ticket-playbook.md and follow it EXACTLY to handle ONE ticket this iteration, then stop. Only output <promise>AFK_RUN_COMPLETE</promise> when the playbook's success-terminal condition is met (no ready tickets remain under the epic)." --max-iterations <N> --completion-promise "AFK_RUN_COMPLETE"
```

After launching, the loop runs autonomously. Each iteration re-reads the playbook, so the
playbook — not your current context — is the source of truth. Do not narrate or babysit;
let it run. The user can `/cancel-ralph` to stop early.

## Termination

- **Success:** a query returns zero ready tickets under the epic → the playbook writes a
  summary to `.claude/afk-report.md` and outputs `<promise>AFK_RUN_COMPLETE</promise>`, which ends the loop.
- **Stop on failure:** an unrecoverable blocker → the playbook discards the failed ticket's
  partial work (keeping the epic branch green), comments on the ticket, writes
  `.claude/afk-report.md`, cancels the loop (`rm -f .claude/ralph-loop.local.md`), and exits
  **without** the promise.
- **Iteration cap:** `--max-iterations` is the backstop if both of the above somehow miss.

When the loop ends, read `.claude/afk-report.md` and summarize the run for the user:
tickets completed (with keys + one-line results), and — if it stopped early — which ticket
blocked it and why.

## The per-ticket playbook

The operational detail lives in [`references/ticket-playbook.md`](references/ticket-playbook.md).
Read it before launching so you understand what the loop will do; the loop reads it every
iteration.
