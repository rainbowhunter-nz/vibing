---
name: afk-implement
description: >-
  Autonomously implement a batch of Jira tickets unattended (AFK). Use this
  whenever the user wants to work through Jira tickets tagged `ready-for-agent`,
  clear a backlog, implement an epic's TODO tickets, or "let it run and implement
  the tickets while I'm away." Trigger even if the user only says something like
  "go implement the ready tickets", "knock out the backlog for PROJ", or "AFK
  implement the auth epic" without naming this skill. An interactive supervisor
  sets up the run, then a ralph loop re-invokes a fresh agent per ticket — each
  implements one ticket on a `wip` branch and leaves it In Review for a human to
  merge. State lives in `.afk/afk-plan.md` so an interrupted run resumes cleanly.
disable-model-invocation: true
---

# AFK Implement

Runs in a devcontainer. Two layers so context resets per ticket and interrupted runs recover: an interactive **supervisor** sets the run up once, then a **ralph loop** (`.afk/run.sh`) re-invokes a fresh **ticket-runner** per ticket while `Run state` is `running` — each starts cold, does one ticket, exits. Durable state = Jira statuses + `.afk/afk-plan.md` + per-ticket plans; nothing in memory, so any crash/halt resumes by reconciling it. Per-role split in **Roles** below.

## Scope & defaults

- Eligible: label `ready-for-agent` AND status `TODO`. Honor narrower user filter (epic, component, single ticket).
- Branch: all work on `wip` (branch from default if missing). **Never push.**
- Commits: runner commits after review passes — ideally one/ticket. Implementer/reviewer subagents stage only; never commit/push.
- Final status: leave each ticket **In Review** for a human. Never Done.
- State: master `.afk/afk-plan.md`; per-ticket `.afk/plans/<ticket>-<title>.md`. `.afk/` gitignored.

## Roles

| Role | Does |
|---|---|
| **Supervisor** (interactive, once) | Pre-flight, batch + order, confirm, write master plan, write + launch driver, then only monitor — never touch the working tree mid-run. |
| **Driver** (`.afk/run.sh`) | Serial loop: one fresh runner at a time while `Run state: running`. Iteration cap guards runaway. |
| **Ticket-runner** (fresh agent/iteration) | Reconcile state, pick next ticket, run ticket cycle, update master plan, exit. No memory of prior iterations. |
| **Implementer / Reviewer** (subagents) | Dispatched per stage by the runner; implement, or review the staged diff independently. |

## Phase 1 — Supervisor setup & launch (once)

A bad start corrupts the whole run — fix everything here first.

1. Git repo, **clean tree**. If dirty, stop + ask.
2. Atlassian MCP authenticated (trivial query). Else start OAuth, wait.
3. `wip` branch exists + checked out (branch from default if needed).
4. `.afk/plans/` exists, `.afk/` gitignored.
5. **Green baseline.** Detect build/test/lint (`package.json`, `Makefile`, `pyproject.toml`, CI) + run. If already red, stop + report. Record commands in master plan — runners read them from there, no re-guessing.
6. **Map Jira workflow.** Confirm real status names + that needed transitions exist: ready (default `To Do`), `In Progress`, review (default `In Review`). These vary by project + are gated by current status; if any differ/missing, ask user to map now. Record mapping in master plan.
7. Query eligible via JQL + user filter, e.g. `labels = "ready-for-agent" AND status = "To Do" AND "Epic Link" = PROJ-42`.
8. For each candidate read **"is blocked by"** links, build dependency order:
   - Blocker **satisfied** if Done/In Review in Jira, or in this batch ordered earlier. (In Review counts — commits already on `wip`; if branch state in doubt, treat unsatisfiable.)
   - Blocker neither satisfied nor in batch = **unsatisfiable** → exclude that ticket + its dependents.
   - Topo-sort the rest, blockers first.
9. Show numbered execution order (ticket, title) + excluded with reasons. **Ask user to confirm.** The one interactive gate.
10. **Write master plan** `.afk/afk-plan.md` per `references/master-plan-template.md`: commands, Jira map, ordered batch (all `pending`), excluded, `Run state: running`.
11. **Write + launch driver** `.afk/run.sh` (below). Launch detached (tmux / `nohup … &`) so the run survives this session; monitor via the Run log. Don't edit repo files while the loop runs — runners own the tree.

### Driver script

Devcontainer, so use `--dangerously-skip-permissions` for unattended runs. Supervisor fills repo path, skill dir, iteration cap (batch size + buffer):

```bash
#!/usr/bin/env bash
set -uo pipefail
REPO="<abs repo path>"
SKILL_DIR="<abs path to this skill>"
PLAN="$REPO/.afk/afk-plan.md"
MAX=<batch size + 5>
cd "$REPO"
i=0
while grep -q '^Run state: running' "$PLAN"; do
  (( ++i > MAX )) && { echo "iteration cap hit"; break; }
  claude -p --dangerously-skip-permissions "AFK_SKILL_DIR=$SKILL_DIR
$(cat "$SKILL_DIR/references/ticket-runner-prompt.md")"
done
echo "loop ended: $(grep '^Run state:' "$PLAN")"
```

## Phase 2 — Ticket cycle (each runner)

The full per-ticket instructions live in `references/ticket-runner-prompt.md` — the driver feeds them to each fresh runner; the supervisor never executes them. That file is **self-contained** (cycle steps, stop conditions, and the review-depth / model-selection / Jira-comment guides) so a runner never has to load this SKILL.md.

Cycle in brief: reconcile state + pick next ticket → scout → plan → implement → independent review → fix ≤3 → commit on `wip` → In Review → comment → update master plan (status, Run log, Handoff). The runner sets `Run state` to `complete` (nothing left) or `halted` (global blocker) to stop the driver.

## Recovery

Every iteration reconciles, so recovery = relaunch:

1. Re-run pre-flight. If `.afk/afk-plan.md` exists with `Run state` running/halted, offer resume vs rebuild.
2. Set `Run state: running` (if halted + blocker cleared), relaunch `.afk/run.sh`. Each runner reconciles per-ticket: `in-progress` but not committed+approved → reset + redo; `done` → skip; `pending` → run in order.

## References

- `ticket-runner-prompt.md` — self-contained per-iteration runner instructions: ticket cycle, stop conditions, and the review-depth / model-selection / Jira-comment guides.
- `master-plan-template.md` — `.afk/afk-plan.md`: run state + recovery anchor.
- `plan-template.md` — per-ticket plan structure + writing guide.
- `implementer-prompt-template.md` — implementer subagent.
- `spec-reviewer-prompt-template.md` — spec reviewer (two-pass only).
- `code-reviewer-prompt-template.md` — code reviewer.
