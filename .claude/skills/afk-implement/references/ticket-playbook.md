# AFK ticket playbook (one ticket per iteration)

You are the **main agent** in a Ralph loop. No memory of prior iterations — this file is the
whole truth. Handle **one ticket**, then stop; the loop re-feeds for the next. Config
(`project`, `cloudId`, `label`, `epic`, `branch`) comes from the loop prompt. Stay scoped to
`<epic>`: only touch its tickets, only commit to `<branch>`.

**Orchestrate, don't type code.** You pick the ticket, gather context, decide the plan,
delegate the build to an implementation subagent, gate it through a review subagent, commit,
end. Keep your own context lean.

## Autonomy rules (govern everything)

- **Never ask the human.** No `AskUserQuestion`, no `ExitPlanMode`, no waiting. If a sub-skill
  wants to quiz the user, answer for them. Tell subagents the same.
- **Ambiguity → most sensible default**: fits conventions/ADRs/vocabulary, smallest change that
  meets the ACs (Simplicity First), reversible. Record the assumption in the closing comment.
- **Risky fork → bail.** High-risk *and* no safe reversible default (irreversible migration,
  destructive external action, security-sensitive change, or a contradiction making "done"
  undefinable) → *Stop on failure*. Don't guess.

## Step 0 — Reconnect + reconcile

- Not on `<branch>` → `git checkout <branch>`.
- Query In-Progress: `project = <project> AND status = "In Progress" AND parent = <epic>` (≤1
  expected). Tickets commit sequentially, so a ticket's commit (if any) is the latest —
  `git log -1 --format=%s <branch>`, check if subject starts with its key (don't grep whole log;
  an old commit or report line can name the key spuriously):
  - **HEAD is this ticket** → committed last run but didn't hand off. Clean tree
    (`git reset --hard HEAD && git clean -fd`), do hand-off (Step 5.2–5.3), continue to Step 1.
  - **HEAD is not this ticket** → interrupted, nothing committed. Discard partials
    (`git reset --hard HEAD && git clean -fd`), adopt it as this iteration's ticket — already
    claimed, resume at Step 2, tell the subagent to skip the claim.
- **No In-Progress ticket** → tree must be clean. Dirty + nothing In-Progress = possible user
  work → *Stop on failure*.

## Step 1 — Pick the next *unblocked* ticket

```
project = <project> AND status = "To Do" AND labels = "<label>" AND issuetype != Epic
  AND parent = <epic>
ORDER BY priority DESC, created ASC
```

- **Zero → success.** Append "RUN COMPLETE" footer (date, epic, branch, count) to
  `.claude/afk-report.md`, output exactly `<promise>AFK_RUN_COMPLETE</promise>`, stop. This
  promise appears nowhere else.
- **Else pick the first ticket whose blockers are all satisfied** (Done or In Review — priority
  order alone is unsafe; don't build on a missing dependency). Blockers come from `is blocked by`
  links (fallback: `## Blocked by` in the description).
- **All blocked → dependency deadlock** (blocker unlabeled or in another epic). *Stop on
  failure*, reason names the waiting ticket and what it waits on.

## Step 2 — Understand + build the context package

Fetch the ticket (description **and** comments). Understand it. Can't read it, or no actionable
ACs → *Stop on failure*.

Do discovery **once, here**, so the subagent doesn't re-spend context on it. Package:

- Ticket: summary, description, ACs, relevant comments.
- Scoped `CLAUDE.md`(s), applicable ADRs, domain vocabulary.
- Pointers to the files/modules involved (you locate; subagent edits).
- Branch name + project check commands (Step 3.3).
- Whether the ticket is **already claimed** (skip the claim transition).
- The autonomy rules (subagent must not prompt either).

## Step 2.5 — Decide everything up front, record it

Before dispatching any subagent, decide the whole iteration and write it to
`.claude/afk-report.md`. Up-front not mid-flight → auditable, no drift. Decide:

- **Implementer model** by difficulty:

  | Ticket shape | Model |
  |---|---|
  | Mechanical, clear spec, 1–2 files | `haiku` |
  | Multi-file feature/integration, moderate reasoning | `sonnet` |
  | Architecture/design-heavy, ambiguous, cross-cutting | `opus` |

- **Review depth** — 1 holistic (small/low-risk) or 2-pass (substantial/risky); see Step 4.
- **Reviewer model** — ≥ implementer's tier, **min `sonnet`**; `opus` for design-heavy.

Append this block (one short reason per choice — the reasoning is the point):

```
## <KEY> <summary>
- Implementer: <model> — <why>
- Review: <1 holistic | 2-pass> @ <reviewer model> — <why>
Steps:
- [ ] Claim → In Progress
- [ ] Implement: <key slices>
- [ ] Verify: <checks + ACs>
- [ ] Review (<depth>)
- [ ] Commit to <branch>
- [ ] Hand off → In Review + comment
Result: (pending)
```

**Tick each box the moment that step finishes — not at the end.** The report is the live run
state: if this iteration crashes, ticked boxes show the next one how far you got. Note fix-loop
rounds under the block. Execute this plan — don't re-decide models or depth later.

## Step 3 — Delegate the build

Dispatch a **fresh implementation subagent** (`Agent`, `model` from Step 2.5) with the context
package. Instruct it to:

1. **Claim** — transition To Do → In Progress (skip if already claimed), brief comment that an
   AFK run started on `<branch>`.
2. **Build test-first** via superpowers, applying the autonomy rules at every prompt:
   `brainstorming` (decide for itself) → `writing-plans` → `test-driven-development` →
   `systematic-debugging` on any surprise. Honor project rules: scoped `CLAUDE.md`s, `uv` for
   Python (never hand-edit `pyproject.toml`), ADRs, minimal+clean (Simplicity First), strictly
   in scope.
3. **Verify** (`verification-before-completion`, evidence not assertions):
   - **Checks pass** (mirror CI): Python from repo root `uv run ruff check src tests &&
     uv run ruff format --check src tests`, `uv run mypy src`, `uv run pytest -q`; web (`apps/web`)
     `pnpm lint`, `pnpm typecheck`, `pnpm test`.
   - **ACs met** — green checks aren't enough (it wrote the tests); confirm each AC with concrete
     evidence.
4. **Report** (don't commit): files touched, AC-by-AC evidence, assumptions, one-line result.

**Leave the work uncommitted — load-bearing.** Review gates the *uncommitted diff*, so the
subagent must **never** `commit`/`reset --hard`/`checkout -- .`/`stash` or otherwise discard its
work (even mid-debugging — fix forward). Say this in its prompt.

Can't get checks green after honest debugging, or an AC unsatisfiable → *Stop on failure*.

## Step 4 — Review gate

Dispatch a **review subagent** on the working-tree diff at the **depth + model from Step 2.5**.
Give it the ACs, the implementer's report, the diff. Must not prompt the user. Depths:

- **1 holistic**: one pass — AC-compliance, correctness, tests, quality together.
- **2-pass**: (1) spec-compliance (`requesting-code-review`) — every AC met, no scope creep,
  assumptions reasonable; then (2) code-quality — correctness, tests exercise the behavior,
  conventions, Simplicity First, no regressions.

Verdict: **APPROVE** (with result summary + AC evidence) or **REQUEST CHANGES** (specific
blocking findings; note what's *not* blocking to keep the fix scoped).

### Fix loop (max 3 rounds)

REQUEST CHANGES → route findings back (`receiving-code-review` — verify, don't blindly comply):

- **Preferred:** continue the same subagent (`SendMessage`) so it keeps context — hand it the
  findings.
- **Fallback (can't resume):** fresh subagent (same model) with context package + current diff +
  prior report + findings. Still no commit/reset.

It fixes, re-verifies (Step 3.3), reports → re-review. One implement→review cycle = one round.
**3 rounds, no approval → *Stop on failure*** (reason "review not converging" + outstanding
findings).

## Step 5 — Commit + hand off

On **APPROVE**:

1. **Commit** to `<branch>` (no push, no PR):
   ```
   git add -A
   git commit -m "<KEY> <concise summary>

   Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
   ```
   Tree clean after.
2. **Review subagent does the Jira hand-off** — hand it the SHA (continue or re-dispatch):
   transition In Progress → In Review, add one short result-focused comment (what was built,
   AC evidence, SHA, assumptions). Concise.
3. **Close the report block**: tick commit + hand-off boxes, set `Result:` to `<SHA> — <one-line
   result>`. The report is the only durable record across iterations.

## Step 6 — End

Stop. Do **not** output the promise (only Step 1's zero case does). The loop re-feeds.

---

## Stop on failure

1. **Keep the branch green** — discard the failed ticket's partials (`git reset --hard HEAD`,
   `git clean -fd` if needed). Earlier commits stay.
2. **Document** — claimed ticket: leave In Progress, comment what was attempted + what blocked it.
   Deadlock (nothing claimed): comment on the waiting ticket (stays To Do) naming its blocker.
3. **Report** — append a "STOPPED" entry to `.claude/afk-report.md`: blocking key, reason,
   tickets done before it.
4. **Cancel** — `rm -f .claude/ralph-loop.local.md`.
5. **Exit** without the promise.
