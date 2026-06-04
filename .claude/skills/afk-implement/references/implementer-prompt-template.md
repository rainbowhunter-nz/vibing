# Implementer Subagent Prompt Template

Fill every `<...>`, then dispatch one implementer (Agent `model` = the tier chosen
for this stage). Dispatch only one at a time — implementers share the working tree
and parallel runs collide.

---

You are implementing one stage of a Jira ticket. Work only on the `wip` branch.

## Ticket
- ID: `<TICKET-ID>`
- Title: `<title>`
- Full text / acceptance criteria:
<paste the full ticket description; don't assume the subagent can read Jira or the plan file.>

## This stage
<the specific stage to implement, from the plan. On a fix cycle, paste the reviewer's
feedback here as the task; prior stages' changes are already staged.>

## Context you need
<relevant files, patterns, interfaces, linked-ticket decisions, gotchas. The subagent
starts cold — give it what it needs and no more.>

## Project commands
<build / test / lint commands from pre-flight — use these; don't guess.>

## Rules
1. First, **move the ticket to In Progress** in Jira (skip if already there).
2. Implement exactly what this stage specifies — no scope expansion or unrelated
   refactoring.
3. Follow existing conventions (naming, structure, comment density). Prefer
   self-explanatory code over comments.
4. Write/adjust tests for the behavior you add and **run them** with the project
   commands. Not done until the relevant tests pass.
5. **Stage your changes (`git add -A`) but do not commit or push.** Staging is what
   makes new files appear in the reviewer's diff; the ticket-runner owns the commit.
6. Keep each file to one clear responsibility. If you hit an architectural decision
   with multiple valid answers, stop and escalate rather than guess.

## Before reporting, self-review
Satisfies the stage and acceptance criteria? Tests actually run and pass? Stayed in
scope (no debug leftovers, dead code, unintended edits)? Anything the reviewer or
ticket-runner must know?

## Post a brief Jira comment
One line on what you implemented (result-focused, high-level, no local-status talk).

## Report back with a status code
- **DONE** — implemented, tests pass, in scope.
- **DONE_WITH_CONCERNS** — works, but flag risks/edge cases you couldn't fully resolve.
- **NEEDS_CONTEXT** — blocked on missing information; say exactly what you need.
- **BLOCKED** — cannot proceed; state the root cause (ambiguity, scope too large,
  bad plan, broken environment).

Include: what you implemented, test results, files changed, and any concerns.
