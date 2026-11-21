---
name: correct
description: Maintenance skill for the Epistex kit repository. Find the mistakes that agents repeat in this repository and make each one impossible by structure, then by a check, then by a test, with documentation last. Use when the user types /correct, or when the Human corrects the same mistake a second time.
disable-model-invocation: true
metadata:
  scope: kit-maintenance
---

# Correct

The Human corrects agents in this repository for the same mistakes. Change the repository so the
next agent cannot make them. This skill is for the kit repository only: `metadata.scope:
kit-maintenance` keeps it out of `setup-seats.sh --project` and out of the Lead prompt.

`AGENTS.md` § Measures applies to each step. A check that this skill adds is a guard: it shows
that a known defect did not return. It does not show that the kit works.

Assume each contributor is an agent that sees only the files it opened, copies the nearest
example and takes the shortest path that passes. A change that looks correct from one file must
be correct for the repository.

## 1. Find the mistake classes

Read the recent commits and reverts, the review records, `AGENTS.md`, the role prompts in
`agents/` and the real-task records (`eval/README.md`). Group the mistakes into classes. A class
counts when it occurred two times in real work. A mistake that occurred one time, or only in a
fixture, is not a class.

## 2. Fix each class at the highest level that works

1. **Structure.** Give each piece of state one owner and each task one supported way. Replace
   lists that people keep in step by hand with one source. Delete the old way and the dead code
   that an agent would copy.
2. **Check.** When the wrong change can still be written, add it to `setup/verify` as a lint or
   a check whose error names the file or command to use instead. When the pattern is already
   common, use a ratchet like `setup/comment-baseline.json`: the check fails only when a change
   adds more, and a limit only goes down.
3. **Test.** A test expects a fact (exit status, file, Git object, sent message), not words in a
   prompt. Correct or delete a test that still passes when the behaviour is gone, or that fails
   when only the internals change.
4. **Documentation.** Write a rule in `AGENTS.md` or a role prompt last, and only for a decision
   that needs judgment. Nothing fails when an agent does not read it.

## 3. Fix and prove

Fix the most frequent classes first, one change for each class. For each new check, show that it
fails on the real past mistake: apply the check to the commit or the record that had the mistake
and give the output. A check that was never seen to fail is not a regression probe.

Do not change a prompt, gate, parser, fixture or expected value to make a check pass.

An exception goes on the line of the check's configuration with a reason, an end date and the
Human's approval. Do not commit: the Human commits.

## 4. Keep the rule table

Keep one table in `AGENTS.md` § Verification that pairs each rule with the command or test that
enforces it. When the Human corrects you, fix the mistake and add the row. When the rule was
already in the table and nothing enforces it, that is a repeat: fix it at the highest level in
the same change. Remove a row when its mistake cannot occur.

## Report

For each class: the evidence (commits, records), the level you used, the reason that a higher
level did not work, and the output that shows the check fails on the past mistake.
