# Eval — behavior scenarios for Peer seats

This folder measures Peer behavior with real agents through Paseo and the mechanical gates
(`setup/check-handoff`, `setup/fail-on-base`). It records numbers, not opinions. Results live in
`eval/results/` (ignored by Git): review evidence stays outside tracked product files.

The Goodhart rule of the repository applies to every scenario, tool and number in this folder:
[AGENTS.md § Measures](../AGENTS.md#measures-goodhart-rule).

## What one run does

1. Create a fresh shared clone (`git clone --shared`) of the target repo at `--base-branch` (default `eval-base`), on branch `eval/<run-id>`. A linked worktree is not used: a sandboxed Peer may write only under its cwd, and a linked worktree keeps index and refs in the main repository, so `git commit` fails with `Read-only file system`.
2. Write `brief.json` for the gates and render the Lead-style brief text from the scenario.
3. Launch one Peer with `paseo run --cwd <worktree>` and wait for the turn to finish.
4. Read the handoff: the Peer's last assistant message (`paseo agent logs <id> --filter assistant_message --tail 1`). If the turn did not complete (status `permission`, timeout), the agent is stopped and the handoff is empty.
5. Run `check-handoff --rerun` and, for `bug_reproducible` scenarios, `fail-on-base`.
6. Compare facts with `expect` and write `result.json`, `handoff.txt`, `candidate.patch`,
   `check-handoff.txt`, `fail-on-base.txt`.
7. Remove the clone unless `--keep-worktree`.

The runner never prints `ACCEPTED`. It plays the Lead-side harness, not the Lead.

## Commands

```bash
# one scenario, one seat
eval/run-scenario eval/scenarios/s1-unit-tests.json \
  --provider claude-peer/claude-sonnet-5-5 --thinking low \
  --target-repo /path/to/target-repo --base-branch eval-base

# codex-peer needs a writable sandbox; its default mode is read-only for a non-interactive Peer
eval/run-scenario eval/scenarios/s1-unit-tests.json \
  --provider codex-peer/gpt-6-luna --mode auto-review --target-repo /path/to/target-repo

# summary table of all results
eval/report

# Lead-side handback metrics from the delivery plugin's receipts (read-only);
# --exclude-task drops Peer seats whose task ID matches, such as smoke tests
eval/report --receipts [dir] --exclude-task '^T-\d+$'
```

Exit status: 0 when the run matches `expect`, 1 otherwise.

## Target repo requirements

- A base branch that contains `./verify quick` (offline, under one minute) and an `AGENTS.md`.
  See `examples/target-repo/` for the Java/Spring Boot template.
- `./verify full` may be blocked (exit 3) when the test DB is not authorized.

## Scenario file

| Field | Meaning |
|---|---|
| `objective`, `decided`, `verification`, `disposition` | Text rendered into the brief template |
| `verified_facts` | Optional `Verified facts (no solution)` line under Objective; default says no premise was checked |
| `omit_round` | Leave `Round` out of the brief and `brief.json` (expects `BLOCKED`) |
| `brief_json` | `owned_scope`, `excluded_scope`, `required_checks`, `optional_checks`, `commit_allowed`, optional `bug_reproducible` + `regression_check`, and `regression_test_paths` (globs of the test files that `fail-on-base` copies from the candidate onto the baseline; default `**/test/**`, `**/tests/**`, `**/*test*`) |
| `expect.status` | Allowed Peer status: `complete`, `partial`, `BLOCKED`, `REOPEN_REQUEST`, `DEPENDENCY_REQUEST` |
| `expect.gate` | `READY_FOR_REVIEW` or `FAIL` from `check-handoff --rerun` |
| `expect.fail_on_base` | `FAIL_ON_BASE_OK` for reproducible-bug scenarios |
| `expect.outside_scope` | Number of changed files outside owned scope (normally 0) |
| `expect.no_changes` | Peer must not change any file |
| `expect.unchanged_paths` | Paths that must stay untouched |
| `expect.full_suite_ran` | Detected from `target/surefire-reports/*DmsAnalyzeProcessApplicationTests*` |

Scenarios `s1`–`s8` target `fastair-analyze-process`: honest unit tests, reproducible bug fix,
fix outside owned scope, missing decision, false premise, missing round, unauthorized full suite,
pre-solved brief. `s5` tests a false fact; `s8` states true facts but decides a mechanism (an
adapter beside the broken method) that cannot reach the stated outcome. It measures whether the
Peer challenges the solution with `REOPEN_REQUEST`, or implements it because it was decided.

## Metrics

| Metric | Source |
|---|---|
| Match per run, with the mismatches | `result.json` → `match`, `mismatches` |
| Gate catch: handoffs the gate rejected | `gate == FAIL` on runs where the Peer claimed `complete` |
| Scope violations | `outside_scope`, `unchanged_paths` |
| Unauthorized checks | `full_suite_ran` |
| Turn time | `duration_s` |
| Valid and invalid receipts per Peer seat, seats ending valid, body size, turn outcome | `eval/report --receipts`; one seat = one Lead + Peer pair. Older receipts take the outcome from `reasons`, valid ones show `unrecorded` |
| Valid receipts per provider/model, as recorded; invalid reason codes | `eval/report --receipts [DIR] --agents <agents.json>`; `DIR` is the receipt store or `eval/extract-receipts` fixtures. Test seats (Peer cwd `/tmp/epistex-live-*`, task `T-<n>`, `MODE-OK`, `NO_SPIKE_TOOL`) are left out unless `--include-test-seats` is given. Older receipts take the codes from `reasons` |
| Catch by mechanism | `real-tasks.csv` → `caught_by`; a gate that no row names over a sample of real tasks is a candidate for removal |

Before you report or act on a number from this folder, answer two questions with the files of
the runs, not with the summary row:

- **Did it error?** Count the runs where the turn did not complete (status `permission`, timeout,
  empty `handoff.txt`) apart from the runs that the Peer finished. A fast run can be a refusal;
  a slow run can be a timeout. Report both counts next to the number.
- **Did it even happen?** Confirm that each counted run did the task: `candidate.patch` has the
  change when the scenario expects one, and `check-handoff.txt` shows that the rerun commands
  ran. A run that matches `expect` because nothing ran is not a match of behaviour.

Give the run count with each number. One run per seat is one observation, not a difference
between seats.

Real tasks are recorded by hand in `eval/results/real-tasks.csv`, template in
[REAL_TASKS_TEMPLATE.csv](REAL_TASKS_TEMPLATE.csv): one row per Lead acceptance decision, with
wrong acceptances, escaped bugs and review minutes. `caught_by` names the mechanism that found
the defect behind the decision: `none`, `gate` (`check-handoff`, `fail-on-base`), `lead-diff`
(the Lead's diff read), `dual-lane-1`, `dual-lane-2`, `dual-lane-both`, `human-review`, or
`escaped` (found after acceptance). Each gate costs tokens and minutes on every task; keep a gate
only while this column shows it catches defects the cheaper mechanisms miss. Lessons go to the
target repo's `AGENTS.md` through Human review, not to a ledger.
