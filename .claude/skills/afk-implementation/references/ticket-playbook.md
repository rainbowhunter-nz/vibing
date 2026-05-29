# AFK ticket playbook (one ticket per iteration)

You are inside a Ralph loop. This file is the source of truth for the iteration — you may
not remember prior iterations, so treat it as complete instructions. Handle **exactly one
ticket**, then stop so the loop re-feeds for the next one. Config (`project`, `cloudId`,
`label`, `epic`, `branch`) comes from the loop prompt. The run is scoped to one epic: only
ever touch tickets parented to `<epic>`, and commit to its branch `<branch>`.

## Autonomy rules (read first — they govern everything below)

You are the user's fully-authorized delegate running unsupervised. Therefore:

- **Never ask the human anything.** Do not use AskUserQuestion or ExitPlanMode, do not wait
  for input, do not stop to "confirm". If a sub-skill (e.g. brainstorming) wants to quiz the
  user, answer on the user's behalf.
- **Resolve ambiguity by picking the most sensible default** — one that (a) fits the project
  conventions, ADRs, and domain vocabulary, (b) is the smallest change that satisfies the
  ticket's acceptance criteria (Simplicity First — nothing speculative), and (c) is
  reversible. Record the assumption in your plan and in the closing ticket comment so a human
  can see what you decided and why.
- **Bail safely on genuinely risky forks.** If a decision is high-risk *and* you cannot pick
  a safe reversible default — irreversible data migration, destructive external action,
  security-sensitive change, or a contradiction in the ticket that makes "done" undefinable —
  do **not** guess. Treat it as an unrecoverable blocker (see *Stop on failure*).

## Step 0 — Reconnect and reconcile

- `git rev-parse --abbrev-ref HEAD` — if not on `<branch>`, `git checkout <branch>`.
- **Reconcile an in-flight ticket.** A crash, context exhaustion, or a failed transition can
  leave a ticket stranded **In Progress** — and since Step 1 only matches `To Do`, it would
  otherwise be silently abandoned. Query for one:
  `project = <project> AND status = "In Progress" AND parent = <epic>` (at most one is
  expected — the loop runs a single ticket at a time). If one exists, grep `git log <branch>`
  for its key to tell apart the two cases:
  - **A commit for it already exists** → a prior iteration finished the work but didn't hand
    off. Make the tree clean (`git reset --hard HEAD && git clean -fd` if needed), then
    complete the hand-off for it (Step 7) and continue to Step 1.
  - **No commit for it** → a prior iteration was interrupted mid-work. Discard any partial
    changes (`git reset --hard HEAD && git clean -fd`), then adopt it as this iteration's
    ticket: skip Step 3 (it's already claimed) and resume from Step 2.
- **No in-flight ticket** → the tree must be clean. A dirty tree with nothing In Progress to
  explain it is genuinely surprising (possible user work) → unrecoverable blocker, *Stop on
  failure*. Otherwise continue to Step 1.

## Step 1 — Pick the next *unblocked* ticket

Query the ready tickets under the epic (the whole list, not just one — you may need to skip
blocked ones):

```
project = <project> AND status = "To Do" AND labels = "<label>" AND issuetype != Epic
  AND parent = <epic>
ORDER BY priority DESC, created ASC
```

- **Zero results → Success terminal.** Append a short run summary to `.claude/afk-report.md`
  (date, epic, branch, the tickets you completed this run with one-line results), then output
  exactly `<promise>AFK_RUN_COMPLETE</promise>` and stop. Do not output that promise in any
  other situation.
- **Otherwise, walk the list in order and pick the first ticket whose blockers are all
  satisfied.** Priority order alone is *not* safe — starting a ticket before its dependency
  exists builds on sand. For each candidate, read its blockers from its `is blocked by` issue
  links (fall back to the `## Blocked by` section of the description). A blocker counts as
  satisfied when its status is **Done** or **In Review** (tickets this run finished are In
  Review). The first candidate with no unsatisfied blocker is your ticket → continue.
- **Every ready ticket is blocked → dependency deadlock.** This happens when a blocker is out
  of scope (unlabeled) or in another epic, so the run can't make progress on its own. Treat it
  as an unrecoverable blocker with reason "dependency deadlock" (name the waiting ticket and
  what it waits on) → *Stop on failure*, so a human can unblock.

## Step 2 — Understand the ticket

Fetch the full ticket: description **and** comments. Read and understand it. If you cannot
read it, or it has no actionable acceptance criteria you can satisfy, that's an unrecoverable
blocker → *Stop on failure*. (Per project CLAUDE.md: always understand the ticket first; STOP
if you can't.)

## Step 3 — Claim it

Transition the ticket **To Do → In Progress** and add a brief comment that an AFK run has
started on branch `<branch>`.

## Step 4 — Implement (superpowers, autonomously)

Work the ticket end-to-end using the superpowers skills, applying the autonomy rules at every
prompt point:

1. `superpowers:brainstorming` — clarify intent and approach, but decide for yourself; capture
   the key decisions and assumptions.
2. `superpowers:writing-plans` — a short, concrete plan for this slice.
3. **Prefer `superpowers:subagent-driven-development`** to execute the plan — it keeps your
   context lean and parallelizes independent parts, which matters across a long unattended run.
   Drop to plain `superpowers:test-driven-development` inline only for a trivial ticket (a
   one-file change, no independent parts) where spawning subagents is pure overhead. Either way,
   build it test-first.
4. `superpowers:systematic-debugging` — on any failure or surprise, before patching blindly.

Honor the project's rules throughout: read the relevant scoped `CLAUDE.md`s; use `uv` for
Python (never hand-edit `pyproject.toml`); follow ADRs and domain vocabulary; keep changes
minimal and clean (Simplicity First). Stay within the ticket's scope — do not implement other
tickets or speculative extras.

## Step 5 — Verify (evidence, not assertions)

Use `superpowers:verification-before-completion`. Two distinct checks — both required:

**a) Project checks pass.** Run the local checks for what you touched and confirm they pass
from real output. Mirror CI:

- Python (`apps/api`, `packages/*`): `uv run ruff check . && uv run ruff format --check .`,
  `uv run mypy src` (api), `uv run pytest -q`.
- Web (`apps/web`): `pnpm lint`, `pnpm typecheck`, `pnpm test`.

**b) Acceptance criteria met.** Green checks are necessary but not sufficient — you wrote the
tests, so a passing suite doesn't prove the ticket is *done*. Walk the ticket's acceptance
criteria one by one and confirm each with concrete evidence (a specific test name, command
output, or observed behavior). Hold this AC-by-AC list — it goes in the Step 7 comment.

If the checks won't go green after honest debugging, or an acceptance criterion can't be
satisfied, that's an unrecoverable blocker → *Stop on failure*. Never commit red.

## Step 6 — Review, then commit to the epic branch

**Self-review first (non-trivial tickets).** Unattended, there's no second pair of eyes, so
supply one: run `superpowers:requesting-code-review` on the diff and resolve blocking findings
(use `superpowers:receiving-code-review` to weigh them — verify, don't reflexively comply). Skip
this only for a trivial one-file change where review is pure overhead.

Then stage and commit onto `<branch>` only — **no push, no PR**:

```
git add -A
git commit -m "<TICKET-KEY> <concise summary>

<short body if useful>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

The tree must be clean after committing.

## Step 7 — Hand the ticket off

Transition **In Progress → In Review** and add one short, result-focused comment: what was
built, the AC-by-AC evidence from Step 5, the commit SHA, and any assumptions you made. Keep it
concise per project CLAUDE.md. Record the same one-line result (key + SHA) for the run report.

## Step 8 — End the iteration

Stop here. Do **not** output the completion promise (that's only for Step 1's zero-result
case). The Ralph loop will re-feed this playbook for the next ticket.

---

## Stop on failure (unrecoverable blocker)

When any step above hits an unrecoverable blocker:

1. **Keep the branch green.** Discard the failed ticket's partial work so the epic branch
   contains only completed tickets: `git reset --hard HEAD` (and `git clean -fd` if needed).
   The commits from earlier tickets this run stay intact.
2. **Document on the ticket.** If you'd already claimed a ticket, leave it **In Progress** and
   comment: what you attempted, what blocked you, and any too-risky decision. If you stopped at
   pick time (dependency deadlock — nothing claimed yet), comment instead on the waiting ticket
   (it stays **To Do**) naming the blocker it's waiting on.
3. **Write the report.** Append a "STOPPED" entry to `.claude/afk-report.md`: the blocking
   ticket key, the reason, and the tickets completed before it.
4. **Cancel the loop:** `rm -f .claude/ralph-loop.local.md` so the Stop hook won't re-feed.
5. **Exit** without outputting the completion promise.
