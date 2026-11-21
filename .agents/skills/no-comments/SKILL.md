---
name: no-comments
description: Maintenance skill for the Epistex kit repository. Spawn Comment Sicko to delete code comments, fix the accepted findings, move decisions to the canonical documents, propose an issue for each known weakness and lower the comment baseline. Use when the user types /no-comments, or when `setup/lint-comments` fails.
disable-model-invocation: true
metadata:
  scope: kit-maintenance
---

# No comments

Code in this repository has no comments (`AGENTS.md` § Verification). A decision lives in the
canonical document of its topic. A known weakness lives in a GitHub issue. `setup/lint-comments`
enforces the rule: `setup/comment-baseline.json` holds the limit of each file, a file that is not
there has a limit of zero, and a limit only goes down.

This skill is for the kit repository only: `metadata.scope: kit-maintenance` keeps it out of
`setup-seats.sh --project` and out of the Lead prompt. It is complete in this folder: each
procedure and the subagent prompt that it names is a file in `references/`.

## Scope

An argument after `/no-comments` is a path or a diff: use it. Without an argument, the scope is
the output of `setup/lint-comments --list` for the files that the current diff against `main`
changes, working tree included. When that diff has no comment, the scope is the full list.

## Steps

1. **Spawn.** Start one subagent with the subagent tool of your harness. Its prompt is: read
   `.agents/skills/no-comments/references/comment-sicko.md`, be that agent, then the scope. Do
   not repeat its rules. Spawn and retry as `references/subagents.md` says. This is a subagent
   of a maintenance session, not a Paseo seat: do not run this skill from a Lead or Peer seat.
2. **Inspect.** Read its report and the diff yourself. Reject the report when it has one of
   these:
   - an edit to code that is not a comment, except `pass` in place of a docstring;
   - a deletion outside the scope;
   - a deleted shebang or tool directive;
   - a `MUST KILL` reason that the code does not support;
   - a `decision` without its full text.

   For a `do not remove` or `IMPORTANT` comment, trace the symbol or read the record
   (`references/why.md`) before you accept the class. When the class is not clear, the comment
   stays deleted and its text goes to step 5 as a `decision`. On a rejected report, revert the
   subagent's edits and run one new subagent with the failure named. Reject a second report,
   report the scope open and stop.
3. **Shape.** Fix a small accepted `MUST KILL` directly: delete a dead path, drop a parameter,
   use the real API. When a fix needs a new shape, make one sketch for the accepted set
   (`references/architect.md`) and stop at the sketch.
4. **Fix.** Implement the smallest root-cause fix inside the scope (`references/root-cause.md`).
   Remove each workaround that a `MUST KILL` names. Do not add a guard for the symptom. Do not
   put the deleted text back as a longer name, a log line or a string. When the root cause is
   outside the scope, make the smallest fix inside it and report the remainder open.
5. **Record.**
   - `decision`: add the fact to the canonical document of its topic, one of the documents that
     `AGENTS.md` lists under "Canonical documentation". Do not make a new document. Keep versions,
     numbers and names exact. Name the file and the function; give no line numbers. When the
     document already says it, add nothing.
   - `excuse` that step 4 did not remove: look for an open issue first
     (`gh issue list --label comment-debt --state open`). When there is none, show the Human the
     title and the text, and file it only after the Human agrees.
   - A constraint that a check can hold (`do not change wording`, `must stay in step with X`):
     offer the cheapest type, runtime check, test or `setup/verify` check inside the scope, and
     wait for the Human's approval before you write it.
6. **Verify.** Run `setup/lint-comments --update` to lower the limits, then `setup/verify`; the
   last line must be `VERIFY OK`. When TypeScript files changed, also run
   `cd plugins/epistex-delivery && npm run typecheck && npm test`.
7. **Report.** Write the report as `references/report-style.md` says: comment lines for each
   class, lines deleted, reports rejected, the sketch, fixes, documents changed, issues proposed
   and filed, checks offered and written, the limits that stay above zero with the reason, and
   the open work. Do not commit: the Human commits.
