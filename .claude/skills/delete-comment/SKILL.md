---
name: delete-comment
description: Delete code comments from this repository. Classify each comment as Tautology, Stale, Excuse or Decision Record; delete it; file an issue for each Excuse; move each Decision Record into the canonical document of its topic; then lower the comment baseline. Use when the user types /delete-comment, when `setup/lint-comments` fails, or when comments must be removed from a file or directory.
---

# Delete comments

Code in this repository has no comments. A decision lives in the canonical document of its topic. A known
weakness lives in a GitHub issue. `setup/lint-comments` enforces the rule with a ratchet:
`setup/comment-baseline.json` holds the comment-line limit of each file, a file that is not there
has a limit of zero, and a limit can only go down.

An argument after `/delete-comment` is a path. Then do the steps for that path only. Without an
argument, do them for every file in the baseline.

## 1. List

Run `setup/lint-comments --list`. Each line is `path:line:text`. The scan covers the tracked
Python, shell, jq, YAML and TypeScript/JavaScript files. A Python docstring is a comment. A shebang
and a tool directive (`# shellcheck`, `# type:`, `# noqa`, `// @ts-…`, `// eslint-…`) are not.

## 2. Classify

Read the code around each comment. Put each comment in one class:

| Class | Test | Action |
| --- | --- | --- |
| Tautology | The code, a name or a test already says it. Section labels and docstrings that repeat a signature are in this class. | Delete. |
| Stale | It names code, a version or a behaviour that is gone. Check the code, the docs and `git log` before you decide. | Delete. |
| Excuse | It gives a reason to keep a weak implementation: a swallowed error, a heuristic in place of a parser, duplicated logic that "must stay in step", a partial read, a version workaround. | Delete. File an issue. |
| Decision Record | It records a decision that the code cannot show: a constraint, an observed backend behaviour, a measured number, a rejected alternative. | Delete. Move the content to a document. |

When a comment is a sound, deliberate trade-off, it is a Decision Record, not an Excuse. When the
code does less than it should and the comment says why that is acceptable, it is an Excuse.

## 3. Act

- **Excuse.** Look for an open issue first: `gh issue list --label comment-debt --state open`.
  If there is none for this weakness, show the Human the title and the text, and file it only
  after the Human agrees (`AGENTS.md`: ask before you publish):
  `gh issue create --label comment-debt --title "<weakness>" --body "<file, what the code does, what it must do>"`.
  The issue text holds the facts of the comment that are still true.
- **Decision Record.** Add the decision to the canonical document of its topic: one of the
  documents that `AGENTS.md` lists under "Canonical documentation" (`README.md`, `docs/setup/…`).
  Do not make a new document or folder. Keep the facts exact: versions, numbers, names, examples.
  Name the file and function the decision applies to. Do not give line numbers. If the document
  already says it, only delete the comment.
- **All classes.** Delete the comment. Delete only the comment: do not change code in the same
  edit. If a docstring was the only statement of a block, put `pass` there. If code reads the
  docstring (`__doc__`), replace that use with a string.

Do not replace a deleted comment with a longer name, a log line or a string that holds the same
text. If the code is not clear without the comment, rename or extract in a separate change.

## 4. Lower the baseline and verify

1. `setup/lint-comments --update` writes the new, lower limits. It refuses to raise one.
2. `setup/verify` must end with `VERIFY OK`.
3. When TypeScript files changed: `cd plugins/epistex-delivery && npm run typecheck && npm test`.

## 5. Report

Give the Human one table: comment lines per class, lines removed, issues filed (with numbers), documents
changed, and the comment lines that stay in the baseline with the reason. Do not commit:
the Human commits.
