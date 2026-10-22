# Target-repository verification template (Java / Spring Boot)

Copy `verify` and `paseo.json` into the root of the repository the agents work on. Adapt the
Maven/Gradle commands to the build. Epistex itself does not run these files.

## `./verify` groups

| Group | Runs | Needs | Who may run it |
|---|---|---|---|
| `quick` | compile + unit tests | nothing shared | Peer, every turn; default `required_checks` |
| `it` | integration tests via Testcontainers | Docker, one port, one DB | only when the brief sets `VERIFY_ALLOW_IT=1` |
| `full` | `quick` then `it` | same as `it` | before Lead acceptance, when the brief authorizes it |

Rules the script enforces:

- `it` and `full` exit `3` with `BLOCKED` when `VERIFY_ALLOW_IT` is not `1` or Docker is not
  reachable. The Peer reports this as `BLOCKED` at verification; it never turns skipped into passed.
- Every command is echoed with `+` and followed by `exit <status>`. Paste these lines into the
  `Verification` cell; `setup/check-handoff` looks for the command string and its exit status.
- `--dry-run` prints the commands without running them; use it to show the Lead what a group does.

Maven expectations: unit tests under Surefire, integration tests under Failsafe in a profile named
`it`, with `skipITs` and `skipUnitTests` properties wired in `pom.xml`. Gradle expectations: tasks
`test` and `integrationTest`. Rename in `verify` if the build differs.

## Port and DB per worktree

A separate worktree does **not** give a separate port or database by itself. `verify` exports:

| Variable | Source | Fallback |
|---|---|---|
| `SERVER_PORT` | `PASEO_WORKTREE_PORT` (set by Paseo for worktree setup, teardown and scripts) | `18000 + hash(branch) % 1000` |
| `DB_NAME` | `DB_NAME` from the environment | `app_<branch slug>` |
| `TESTCONTAINERS_REUSE_ENABLE` | environment | `false`, so each run gets a fresh MariaDB/MySQL container |

Read `SERVER_PORT` and `DB_NAME` in `application-test.yml` (for example
`spring.datasource.url: jdbc:mariadb://localhost:3306/${DB_NAME}` when a shared DB is used).
With Testcontainers the container owns its DB, so `DB_NAME` only matters for a shared instance.

## `paseo.json`

- `worktree.setup` runs once when Paseo creates a worktree: copy local env files from the source
  checkout and warm the Maven cache. Setup failure stops the worktree; keep it fast and offline-safe.
- `worktree.teardown` removes containers labelled for this branch. Testcontainers only labels
  `org.testcontainers=true`; add `paseo.branch=$PASEO_BRANCH_NAME` through
  `withLabel` in the test base class if you want per-branch cleanup.
- `scripts.quick/it/full` wrap `./verify` so Lead and Peer start them through
  `paseo script start <name>` and read the exit code from the supervised terminal.
- `scripts.app` is a `service`: Paseo allocates `PASEO_PORT` and a proxy URL per worktree.
  Only start it when the brief allows holding a port.

## What to write in the brief

- `required_checks`: `["./verify quick"]` for routine changes.
- `optional_checks`: `["./verify it"]` or `["./verify full"]`, plus the sentence that grants
  Docker, port and DB for this turn. Without that sentence the Peer reports `BLOCKED`.
- Record in the target repository's `AGENTS.md` (see `../AGENTS_MD_SNIPPET.md`, section
  *Authority → environment boundaries*) which groups a Peer may run without asking.
