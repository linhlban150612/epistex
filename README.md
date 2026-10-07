# Epistex — standalone agent roles on Paseo

Epistex provides role prompts and launchers for Paseo; Seatworks is not required. The kit
provides Codex Lead/Peer and Devin ACP Supervisor seats, with Paseo as the sole control plane.
There is no desk, 21-provider installer, patrol, or `epx-*` profile.

| Role | Responsibility | Paseo MCP in provider |
|---|---|---|
| Supervisor | Cross-project observation, opening Leads, helping the Human, and event-triggered interventions (permissions, cancel, mode); writes, receives, and reviews no artifacts | Enabled |
| Lead | Assigning tasks, requesting rework, and deciding acceptance | Enabled |
| Peer | Implementing within owned scope, verification, and handoff | Disabled |

Human implementation requests normally authorize the Lead to assign Peers and review/rework
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

Lead/Peer Codex and runtime safeguards are described in [SETUP.md](SETUP.md) and the
[runtime guide](docs/setup/codex-runtime.md); seats on other
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

## Paseo-only workflow and Codex runtime

Detailed workflow ownership, runtime layout, resume selection, environment variables,
Seatworks compatibility, and Codex isolation checks: [runtime and workflow guide](docs/setup/codex-runtime.md).

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
