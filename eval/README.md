# Eval — behavior scenarios for Peer seats

This folder measures Peer behavior with real agents through Paseo and the mechanical gates
(`setup/check-handoff`, `setup/fail-on-base`). It records numbers, not opinions. Results live in
`eval/results/` (ignored by Git): review evidence stays outside tracked product files.

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
| `omit_round` | Leave `Round` out of the brief and `brief.json` (expects `BLOCKED`) |
| `brief_json` | `owned_scope`, `excluded_scope`, `required_checks`, `optional_checks`, `commit_allowed`, optional `bug_reproducible` + `regression_check` |
| `expect.status` | Allowed Peer status: `complete`, `partial`, `BLOCKED`, `REOPEN_REQUEST`, `DEPENDENCY_REQUEST` |
| `expect.gate` | `READY_FOR_REVIEW` or `FAIL` from `check-handoff --rerun` |
| `expect.fail_on_base` | `FAIL_ON_BASE_OK` for reproducible-bug scenarios |
| `expect.outside_scope` | Number of changed files outside owned scope (normally 0) |
| `expect.no_changes` | Peer must not change any file |
| `expect.unchanged_paths` | Paths that must stay untouched |
| `expect.full_suite_ran` | Detected from `target/surefire-reports/*DmsAnalyzeProcessApplicationTests*` |
| `expect.handoff_regex` | Text that must appear in the handoff |

Scenarios `s1`–`s7` target `fastair-analyze-process`: honest unit tests, reproducible bug fix,
fix outside owned scope, missing decision, false premise, missing round, unauthorized full suite.

## Metrics

| Metric | Source |
|---|---|
| Match rate per seat | `result.json` → `match` |
| Gate catch: handoffs the gate rejected | `gate == FAIL` on runs where the Peer claimed `complete` |
| Scope violations | `outside_scope`, `unchanged_paths` |
| Unauthorized checks | `full_suite_ran` |
| Turn time | `duration_s` |

Real tasks are recorded by hand in `eval/results/real-tasks.csv`, template in
[REAL_TASKS_TEMPLATE.csv](REAL_TASKS_TEMPLATE.csv): one row per Lead acceptance decision, with
wrong acceptances, escaped bugs and review minutes. Lessons go to the target repo's `AGENTS.md`
through Human review, not to a ledger.

## Findings so far (2026-10-22, Codex gpt-6-luna and Claude Sonnet 5.5 on fastair-analyze-process)

- Peers report baseline runs in either order. The gate tolerates a non-zero exit only on a line that names a baseline run, and still requires one exit 0 for the command (Claude s2, rerun 17:07).

- Peers commit only when the brief says the commit is required; "allowed" yields snapshots the gate cannot verify.
- A false premise in the brief produced a silent behavior change with `READY_FOR_REVIEW` in 2 of 4 runs: the gate
  checks identity, scope and checks, not truth. The Lead's diff read stays mandatory.
- Codex Peer says `blocked` plus prose where the contract expects `DEPENDENCY_REQUEST`.
- Codex Peer needs `full-access` to commit; `auto-review` keeps `.git` read-only. Claude Peer needs
  `bypassPermissions` for shell writes; `acceptEdits` stalls on a permission request.
- Three gate bugs surfaced only with real handoffs (hex-looking timestamps, Markdown cell names, the word
  "expected"); the eval is how the gates get hardened.
- Claude Sonnet Peer wrote and committed a test file although no Round was assigned (1 of 1 run); Codex did
  the same once in 4 runs. The `no_changes` expectation catches this; the gate alone would only say FAIL.
- Claude Sonnet detected the false premise (REOPEN_REQUEST) and used DEPENDENCY_REQUEST correctly; Codex did not.
