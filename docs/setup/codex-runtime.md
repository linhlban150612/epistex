# Codex runtime, resume, and environment

This guide documents Codex runtime selection, resume behavior, environment compatibility and the
Codex Supervisor pin. Common prerequisites are in [SETUP.md](../../SETUP.md). Backend-specific seat setup remains in the linked
[backend guides](.).

## Codex runtime and resume

```text
Paseo provider → setup/codex-room <role> (sync runtime, then exec Codex)
  → ~/.codex-runtime/epistex/<project-id>/<role>/
       config.toml          generated runtime configuration, model_instructions_file → role-instructions.md
       role-instructions.md generated, COMMON.md + selected role
       auth.json            → canonical Codex home
       skills/, plugins/    → canonical Codex home
       sessions/logs/...    private mutable state
  → Codex at the wrapper-selected working directory
```

Git root, subdirectories, and linked worktrees share role runtime through the shared Git directory;
the usual `.git` layout retains the old main-checkout path hash. Outside Git (or when Git is
unavailable), identity is based on the absolute path. If set, `EPISTEX_PROJECT_ROOT` selects both
the project and launch CWD; otherwise, the launcher's `$PWD` is used.

Sync links shared resources from the canonical home, parses/round-trips TOML, applies the prompt,
and disables `agents.enabled`, `features.multi_agent`, and `features.multi_agent_v2`. For Peer, it
removes the MCP server named `paseo` from runtime config. Canonical config is not modified. Sync
preserves private sessions/logs/database, rejects runtime or ancestor symlinks, and preflights
conflicts; replacing each of `config.toml` and `role-instructions.md` is atomic, not the
entire sync. Instructions are resolved from the kit, not the project CWD; missing sources
or common + role text over 16 KiB block sync before runtime changes.

UUID resume can find the same-role runtime in both the `epistex` and `seatworks` namespaces; it
does not copy the session:

```bash
setup/codex-room peer exec resume '<session-UUID>' --json 'Continue the assigned task'
```

Use the UUID immediately after `resume`, and put options after the UUID, not before the command or
UUID; the `e resume <UUID>` alias is also supported. If there are zero or multiple matching
runtimes, stop. Picker, session name, `--last`, and other layout arguments use only the current
project runtime. The wrapper **does not read session IDs from app-server RPC**; changing CLI
routing does not prove that an old Supervisor in Paseo can resume.

### Skills after compaction

Codex custom skills live in `$CODEX_HOME/skills/`; in a role runtime that directory links to the
canonical Codex home (see the tree above). The skill list does not survive a context compaction,
so a Codex Lead re-reads `$CODEX_HOME/skills/` instead of relying on memory. The kit's Lead skills are
not in `$CODEX_HOME/skills/`; they are installed into the project's `.agents/skills/`
([SETUP.md step 6](../../SETUP.md#6-set-the-contract-and-protocol-in-the-target-project)).

### Environment variables and Seatworks compatibility

| Variable | Default / purpose |
|---|---|
| `EPISTEX_PROJECT_ROOT` | Launcher CWD for Codex when the project must be pinned |
| `EPISTEX_CODEX_HOME` | `~/.codex`; canonical config and shared-resource source |
| `CODEX_BIN` | Codex executable; defaults to looking up `codex` on PATH |
| `PASEO_CONFIG` | Config file used by the seat checker |
| `PASEO_HOME` | Seat checker uses `<PASEO_HOME>/config.json` if `PASEO_CONFIG` is unset |

`SEATWORKS_PROJECT_ROOT` and `SEATWORKS_CODEX_HOME` are fallbacks for their corresponding
`EPISTEX_*` variables; a non-empty new value takes precedence. An old runtime under
`.codex-runtime/seatworks` is used in place if it is the sole match for project/role. If both old
and new runtimes exist, ordinary launch reports ambiguity. There is no bulk migration; do not
delete/copy data to fix resume.

### Peer sandbox and worktrees

Paseo mode `auto-review` gives the Codex Peer a workspace-write sandbox without approval waits; the provider default
`auto` leaves a non-interactive Peer read-only (`Read-only file system` on every write, including `./verify`).
Writable roots are the session cwd only, and the sandbox keeps `.git` read-only, so `git commit` fails with
`index.lock: Read-only file system` in a linked worktree and in a full clone alike. With `auto-review` the Peer
can only hand off an uncommitted snapshot, which `setup/check-handoff` reports as UNSUPPORTED. A committed
candidate needs `full-access` (no sandbox); the Human decides this per project in `WORKSPACE_PROTOCOL.md`.

## Supervisor pin

| Seat | Launcher args | Model | Thinking/profile pins |
|---|---|---|---|
| `codex-supervisor` | `codex-room supervisor` | `gpt-6-astra` | low, medium |

Do not pin the Supervisor CWD through env: its workspace `~/work/SUPERVISOR` stays empty and the prompt confirms the CWD itself.
