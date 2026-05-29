# AFK ticket playbook (one ticket per iteration)

You are inside a Ralph loop. This file is the source of truth for the iteration — you may
not remember prior iterations, so treat it as complete instructions. Handle **exactly one
ticket**, then stop so the loop re-feeds for the next one. Config (`project`, `cloudId`,
`label`, `branch`) comes from the loop prompt.

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

## Step 0 — Reconnect

- `git rev-parse --abbrev-ref HEAD` — if not on `<branch>`, `git checkout <branch>`.
- `git status` — the tree must be clean. If it is dirty, a previous iteration left a mess:
  this is an unrecoverable blocker → *Stop on failure*.

## Step 1 — Pick the next ticket

Query Jira (limit 1):

```
project = <project> AND status = "To Do" AND labels = "<label>" AND issuetype != Epic
ORDER BY priority DESC, created ASC
```

- **Zero results → Success terminal.** Append a short run summary to `.claude/afk-report.md`
  (date, branch, the tickets you completed this run with one-line results), then output
  exactly `<promise>AFK_RUN_COMPLETE</promise>` and stop. Do not output that promise in any
  other situation.
- **One result →** that's your ticket for this iteration. Continue.

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
3. `superpowers:test-driven-development` (and `superpowers:subagent-driven-development` when the
   plan has independent parts) — build it test-first.
4. `superpowers:systematic-debugging` — on any failure or surprise, before patching blindly.

Honor the project's rules throughout: read the relevant scoped `CLAUDE.md`s; use `uv` for
Python (never hand-edit `pyproject.toml`); follow ADRs and domain vocabulary; keep changes
minimal and clean (Simplicity First). Stay within the ticket's scope — do not implement other
tickets or speculative extras.

## Step 5 — Verify (evidence, not assertions)

Use `superpowers:verification-before-completion`: run the project's local checks for what you
touched and confirm they pass from real output. Mirror CI:

- Python (`apps/api`, `packages/*`): `uv run ruff check . && uv run ruff format --check .`,
  `uv run mypy src` (api), `uv run pytest -q`.
- Web (`apps/web`): `pnpm lint`, `pnpm typecheck`, `pnpm test`.

If checks will not go green after honest debugging, that's an unrecoverable blocker →
*Stop on failure*. Never commit red.

## Step 6 — Commit to the shared branch

Stage and commit onto `<branch>` only — **no push, no PR**:

```
git add -A
git commit -m "<TICKET-KEY> <concise summary>

<short body if useful>

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

The tree must be clean after committing.

## Step 7 — Hand the ticket off

Transition **In Progress → In Review** and add one short, result-focused comment (what was
built/verified, plus any assumptions you made). Keep it concise per project CLAUDE.md.

## Step 8 — End the iteration

Stop here. Do **not** output the completion promise (that's only for Step 1's zero-result
case). The Ralph loop will re-feed this playbook for the next ticket.

---

## Stop on failure (unrecoverable blocker)

When any step above hits an unrecoverable blocker:

1. **Keep the branch green.** Discard the failed ticket's partial work so the shared branch
   contains only completed tickets: `git reset --hard HEAD` (and `git clean -fd` if needed).
   The commits from earlier tickets this run stay intact.
2. **Document on the ticket.** Leave it **In Progress** and comment: what you attempted, what
   blocked you, and any decision that was too risky to make alone.
3. **Write the report.** Append a "STOPPED" entry to `.claude/afk-report.md`: the blocking
   ticket key, the reason, and the tickets completed before it.
4. **Cancel the loop:** `rm -f .claude/ralph-loop.local.md` so the Stop hook won't re-feed.
5. **Exit** without outputting the completion promise.
