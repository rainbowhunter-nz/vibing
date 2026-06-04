---
name: afk-implement
description: Autonomously implement every `ready-for-agent` Jira ticket under one epic, hands-off, via a Ralph loop. Each iteration the main agent picks the next unblocked ticket, delegates the build to an implementation subagent (model chosen by difficulty), gates it through a separate review subagent (approve / send-back-to-fix), commits the approved change to the epic branch (`VIB-<n>-<slug>`), and moves on. Use whenever the user wants to clear an epic's backlog unattended — "AFK", "overnight run", "work through the ready tickets in this epic", "batch-implement the open tickets", "hands-off / unsupervised implementation". Scoped to the vibing (VIB) Jira project.
disable-model-invocation: true
---

# AFK Implement

Clear one epic's `ready-for-agent` backlog, no human present. Pre-flight resolves the epic +
branch and gets one go-ahead; then a **Ralph loop** (`/ralph-loop`) runs the backlog. Each
iteration = one **main agent** handling one ticket: orchestrate an **implementation subagent**
(builds) and a **review subagent** (gates), commit the approved change to the epic branch, end.
The loop re-feeds the playbook for the next ticket. Ends when no ready tickets remain (success)
or a ticket hits an unrecoverable blocker (stop).

## Roles

- **Main agent** (each iteration): orchestrator. Reconnect, pick next unblocked ticket, gather
  context, decide each subagent's model, run the implement↔review loop, commit, end. Supervises
  — doesn't write code or review itself.
- **Implementation subagent**: claims (To Do → In Progress), builds test-first, verifies,
  reports. Fresh per ticket; continued in place on review fixes.
- **Review subagent**: gates. Main scales depth — 1 holistic pass (small) or 2-pass
  (spec-compliance then code-quality, substantial). Approves or returns blocking findings; on
  approve owns the Jira hand-off (→ In Review + result comment).

## Operating decisions (fixed — don't "improve" mid-run)

- **Scope gate:** only `To Do` + `ready-for-agent` label + parented to the target epic. The
  label is the opt-in — never touch unlabeled tickets, never leave the epic.
- **One epic per run.** Second epic → another run.
- **Dependency-aware order:** `Blocked by` order, not raw priority — skip until blockers are
  Done/In Review.
- **Isolation:** one branch per run (`VIB-<n>-<slug>`), sequential commits. No per-ticket
  branches, no PRs, no pushing.
- **Unrecoverable failure → stop the whole loop and report.** One bad ticket ends the session.
- **Autonomy after pre-flight:** never prompts the human again (see playbook's autonomy rules).

## Config and defaults

Optional args; else:

| Setting | Default | Notes |
|---|---|---|
| `project` | `VIB` | Jira project key |
| `cloudId` | `70b0455e-11e5-47f8-8c2a-f91ba4065e51` | rainbowhunter Atlassian site |
| `label` | `ready-for-agent` | scope gate |
| `epic` | — | target epic key (e.g. `VIB-5`); if omitted, inferred in pre-flight |
| `branch` | `VIB-<n>-<slug>` | epic key + slugified summary, e.g. `VIB-5-product-foundation` |

Jira MCP must be reachable (use the `cloudId` above). If not, STOP — don't start a loop you
can't drive.

## Phase 1 — Pre-flight (once, this turn, before launching)

The **only** phase where prompting the user is allowed.

1. **Verify Jira** — MCP answers, project/cloudId resolve. STOP if not.
2. **Resolve the epic.** Use the passed `epic`; else survey ready tickets project-wide, group
   by parent. One epic → it. Several → most ready tickets (tie-break: priority, then oldest).
   Slugify the epic summary → `VIB-<n>-<slug>` (lowercase, spaces/underscores → hyphens, drop
   other punctuation, ~5 words). E.g. `VIB-5` "Product Foundation" → `VIB-5-product-foundation`.
3. **Survey:**
   ```
   project = <project> AND status = "To Do" AND labels = "<label>"
     AND issuetype != Epic AND parent = <epic>
   ORDER BY priority DESC, created ASC
   ```
   Count 0 → say so, stop.
4. **Clean tree + fresh base.** `git status` clean (STOP if dirty). From up-to-date `main`,
   `git checkout -b VIB-<n>-<slug>`. Already exists → STOP and surface it.
5. **Confirm, then go.** Report epic, branch, count, keys; ask one go-ahead (`AskUserQuestion`).
   On yes, launch. **Last prompt** — everything after runs unattended.
6. **Safety net:** `--max-iterations` = `ready_count + 2`.

## Phase 2 — Launch the loop

Defer per-ticket detail to the playbook so the re-fed prompt stays small:

```
/ralph-loop "AFK implement run. Config: project=<project>, cloudId=<cloudId>, label=<label>, epic=<epic>, branch=<branch>. Read .claude/skills/afk-implement/references/ticket-playbook.md and follow it EXACTLY to handle ONE ticket this iteration, then stop. Only output <promise>AFK_RUN_COMPLETE</promise> when the playbook's success-terminal condition is met (no ready tickets remain under the epic)." --max-iterations <N> --completion-promise "AFK_RUN_COMPLETE"
```

Each iteration re-reads the playbook — it, not your context, is the source of truth. Don't
narrate or babysit. User can `/cancel-ralph`.

## Termination

- **Success:** zero ready tickets → playbook outputs `<promise>AFK_RUN_COMPLETE</promise>`.
- **Stop on failure:** unrecoverable blocker → playbook keeps the branch green, documents on the
  ticket, writes the report, cancels the loop (`rm -f .claude/ralph-loop.local.md`), exits
  **without** the promise.
- **Iteration cap:** `--max-iterations` backstops both.

When the loop ends, read `.claude/afk-report.md` and summarize: tickets completed (keys +
one-liners), and if stopped early, which ticket blocked it and why.

## The per-ticket playbook

Detail lives in [`references/ticket-playbook.md`](references/ticket-playbook.md). Read it
before launching; the loop reads it every iteration.
