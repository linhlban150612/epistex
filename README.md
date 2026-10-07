# Epistex — standalone agent roles on Paseo

Epistex provides role prompts and launchers for Paseo; Seatworks is not required. The kit
provides Codex Lead/Peer and Devin ACP Supervisor seats, with Paseo as the sole control plane.
There is no desk, 21-provider installer, patrol, or `epx-*` profile.

| Role | Responsibility | Paseo MCP in provider |
|---|---|---|
| Supervisor | Cross-project observation, opening Leads, and helping the Human; does not receive or review artifacts | Enabled |
| Lead | Assigning tasks, requesting rework, and deciding acceptance | Enabled |
| Peer | Implementing within owned scope, verification, and handoff | Disabled |

Human implementation requests normally authorize the Lead to assign a Peer and review/rework
within scope, unless the Human limits delegation. The Peer is the sole writer for implementation,
tests, config, documentation, and conflict resolution, including one-line changes. The Lead reads,
verifies, and accepts or requests rework; if the Peer is blocked, the Lead reports blocked and does
not write in their place. Read-only requests do not authorize agent creation; delegation does not
authorize automation, model/effort changes, pushing, or deployment.

Backends: **Claude, Codex, Devin, Pi, Amp, GLM, Droid**. Codex loads prompts with
`model_instructions_file`. Claude adds the role to `appendSystemPrompt` in the SDK
`initialize` message when using stream-json, or uses `--append-system-prompt` outside the SDK.
Pi uses native launch instructions. Devin/Amp/GLM/Droid use the ACP proxy, which adds role
instructions to each session's first prompt during the proxy lifecycle — **not the system prompt**.
Droid does not support Paseo MCP through this configuration.

This is coordination among agents running as the same Unix user, **not an OS sandbox**. Read-only
and owned scope are contract/prompt rules, not restrictions on arbitrary shell use. Disabling MCP
does not absolutely prevent an agent from invoking the CLI. The kit does not implement Seatworks'
full gate, incident, merge, or permissions engine. Successful configuration checks do not prove
that every backend can launch.

## Install the Codex seats and Supervisor

Requires a configured Paseo CLI/daemon, Python **3.11+**, and the executable and credentials for
the backend you want to use. Codex requires Bash and the canonical `config.toml`. Git is used to
identify the common root, subdirectories, and linked worktrees.

From the kit directory, after authorizing changes to Paseo configuration, run:

```bash
bash setup/setup-seats.sh --check
```

Merge the three entries in `examples/paseo-providers.json` into `.agents.providers` in the
existing config; replace `<KIT>` with the absolute path and remove `_doc`. Do not replace the
entire config file. Enable MCP injection; enable provider tools for Lead and Supervisor and disable
them for Peer. Supervisor runs only from the empty workspace `~/work/SUPERVISOR`; its prompt
checks the exact CWD. Supervisor discovers workspaces, agents, providers, and models through Paseo,
not a registry.

Lead/Peer Codex and runtime safeguards are described in [SETUP.md](SETUP.md); seats on other
backends, including the Devin Supervisor, are in [docs/setup/](docs/setup/) and linked from it. Run:

```bash
bash setup/setup-seats.sh
paseo reload
bash setup/setup-seats.sh --check
```

`setup-seats.sh` does not edit global config; without `--check`, it checks the three seats and sets
the executable bit. The checker also requires `jq`. The sample selects Lead `gpt-6.1-sol/low`,
Peer `gpt-6-luna/low`; Supervisor uses the Devin ACP model/effort selected in the provider table.
Do not put project-specific policy in provider config.

## Paseo-only workflow

Supervisor observes through Paseo; the Lead owns coordination structure, routing, review, and
acceptance. The Peer is the sole writer. Supervisor opens a Lead in the project workspace and
does not create a Peer.

| Step | Coordination mechanism / owner |
|---|---|
| Discovery | Supervisor uses Paseo `list_workspaces`, `list_agents`, `list_providers`, `list_models` |
| Assignment | Supervisor opens a Human-authorized Lead with `create_agent(workspaceId=...)`; passes the Supervisor agentId in `initialPrompt` |
| Implementation | Lead defines scope and creates a Peer through Paseo; Peer is the sole writer |
| Handoff | Peer sends all six items directly to Lead, including candidate identification details |
| Review | Lead reads the exact candidate and evidence; complex/review tasks use Dual-Lane review (two read-only Peers on different backends, Lead arbitrates); Human reviews when risk is high |
| Rework | Lead sends exactly one `send_agent_prompt` specifying task, round, base SHA, rejected candidate, and feedback |
| Acceptance | Lead decides; Supervisor does not decide in their place |
| Archiving | Supervisor archives the Lead when the Human confirms the project is closed |

There is no coordination desk, registry, ledger, patrol, timer, recurring schedule, or heartbeat.
Paseo messages are the communication channel; idle/notification status does not prove that work
is complete.

## Codex runtime and resume

```text
Paseo provider → setup/codex-room <role> → setup/codex-room-sync
  → ~/.codex-runtime/epistex/<project-id>/<role>/
       config.toml          generated, role prompt
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
conflicts; **only replacing `config.toml` is atomic**, not the entire link update.

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

## Policy, verification, and key files

Role prompts maintain stable behavior; the product repo's `AGENTS.md` holds shared invariants;
`WORKSPACE_PROTOCOL.md` is the coordination policy read by the Lead; and the task brief passes
specific constraints to the Peer. Keep logs and receipts outside Git. Use templates in `examples/`
according to the target repo's hygiene; do not commit process documents into every repo.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
bash -n setup/codex-room
bash -n setup/setup-seats.sh
git diff --check
```

Tests use fixtures and temporary config/state; they do not replace auth, model, backend launch,
actual CWD, or live recovery checks.

### Cautions and known limitations

- All roles run as the same Unix user; scope and tool visibility are not an OS sandbox (see above).
- Paseo is the sole agent control plane and owns lifecycle and topology; the former desk control
  plane and patrol installer were removed. Desk, patrol, daemon, timer, ledger, agent-ID and plan
  details in Git history describe past state only; never treat them as instructions to inspect,
  mutate, or recover retained external state. Inspect live state before operating.
- The `setup/codex-room-sync` contracts above (preserve private runtime data and canonical config,
  disable native multi-agent features, reject ambiguous or symlinked runtimes) are current
  behaviour, covered by `tests/test_codex_room_sync.py` and `tests/test_codex_room.py`.
- ACP child-exit handling was a reported limitation: `setup/role-agent` forwards stdin until EOF,
  so a backend that exits early may surface only on the next input. Not re-reproduced; reproduce
  against current code before relying on it.

### Key files

| Path | Role |
|---|---|
| `agents/*.md` | Supervisor, Lead, and Peer prompts |
| `setup/role-agent` | Native Claude/Pi launcher and ACP instruction proxy |
| `setup/codex-room`, `setup/codex-room-sync` | Select runtime/resume and generate Codex config |
| `setup/setup-seats.sh`, `examples/paseo-providers.json` | Three role seats and provider check |
| `SETUP.md` | Setup entry point: common steps, Codex seats, live verification |
| `docs/setup/*.md` | Backend-specific seats: Claude, Amp, Pi/OMP, Devin/Copilot/Cursor |
| `examples/AGENTS_MD_SNIPPET.md`, `examples/WORKSPACE_PROTOCOL.md` | Contract/policy templates for target repos |
| `tests/` | Runtime, role launcher, and seat-checker regression tests |
