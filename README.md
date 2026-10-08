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

Backends: **Claude, Codex, Devin, Pi, Amp, GLM, Droid, Antigravity**. Codex loads prompts with
`model_instructions_file`. Claude adds the role to `appendSystemPrompt` in the SDK
`initialize` message when using stream-json, or uses `--append-system-prompt` outside the SDK.
Pi uses native launch instructions. Devin/Amp/GLM/Droid/Antigravity use the ACP proxy, which adds role
instructions to each session's first prompt during the proxy lifecycle — **not the system prompt**.
Droid does not support Paseo MCP through this configuration.

This is coordination among agents running as the same Unix user, **not an OS sandbox**. Read-only
and owned scope are contract/prompt rules, not restrictions on arbitrary shell use. Disabling MCP
does not absolutely prevent an agent from invoking the CLI. The kit does not implement Seatworks'
full gate, incident, merge, or permissions engine. Successful configuration checks do not prove
that every backend can launch.

## Install the Codex seats and Supervisor

Requires a configured Paseo CLI/daemon, Python **3.11+**, Bash, Git, `jq`, Codex, and
credentials for the selected backend. Preserve the existing Paseo/Codex configuration and
runtime state; the kit is not an OS sandbox and configuration checks do not prove a live launch.
Follow [SETUP.md](SETUP.md) for installation and live verification; backend-specific instructions
are in [docs/setup/](docs/setup/), including [Antigravity](docs/setup/antigravity.md).

## Paseo-only workflow

Supervisor observes through Paseo and acts only on events; the Lead owns coordination structure,
routing, review, and acceptance. The Peer is the sole writer; there is no dedicated Reviewer agent.
Supervisor opens a Lead in the project workspace and does not create a Peer.

| Step | Coordination mechanism / owner |
|---|---|
| Discovery | Supervisor uses Paseo `list_workspaces`, `list_agents`, `list_providers`, `list_models` |
| Assignment | Supervisor opens a Human-authorized Lead with `create_agent(workspaceId=...)`; passes the Supervisor agentId in `initialPrompt` |
| Implementation | Lead defines scope and creates a Peer through Paseo; Peer is the sole writer |
| Handoff | Peer sends all six items directly to Lead, including candidate identification details |
| Review | Lead reads the exact candidate and evidence. Complex/review tasks use Dual-Lane review: two read-only Peers (`claude-peer` + `codex-peer`), same neutral brief, unaware of each other; shared findings are high-confidence, divergences get blind cross-critique (at most 2 rounds), Lead arbitrates, no third Peer. Human reviews when risk is high |
| Rework | Lead sends exactly one `send_agent_prompt` specifying task, round, base SHA, rejected candidate, and feedback |
| Intervention | Only on an event (notification, Lead question, Human request), Supervisor may use `list_pending_permissions`, `respond_to_permission`, `cancel_agent`, `set_agent_mode`, then tells the owning Lead |
| Loops / reset | Loops are counted in events, never time. Lead proposes a context reset (archive the stuck agent; a new agent resumes from the frozen base/candidate SHA); only the Human confirms, via Supervisor |
| Acceptance | Lead decides; Supervisor does not decide in their place |
| Archiving | Supervisor archives the Lead when the Human confirms the project is closed |

There is no coordination desk, registry, ledger, patrol, timer, recurring schedule, or heartbeat.
Paseo messages are the communication channel; idle/notification status does not prove that work
is complete.

## Codex runtime and resume

Detailed workflow ownership, runtime layout, resume selection, environment variables,
Seatworks compatibility, and Codex isolation checks: [runtime and workflow guide](docs/setup/codex-runtime.md).

## Policy and verification

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

- Context compaction is backend-dependent; some seats remain unconfigured and Devin is user-wide,
  not workspace-scoped. See [context compaction](docs/setup/context-compaction.md).

- All roles run as the same Unix user; scope and tool visibility are not an OS sandbox (see above).
- Paseo is the sole agent control plane and owns lifecycle and topology; the former desk control
  plane and patrol installer were removed. Desk, patrol, daemon, timer, ledger, agent-ID and plan
  details in Git history describe past state only; never treat them as instructions to inspect,
  mutate, or recover retained external state. Inspect live state before operating.
- `setup/codex-room-sync` preserves private runtime data and canonical config, disables native
  multi-agent features, and rejects ambiguous or symlinked runtimes. These contracts are covered by
  `tests/test_codex_room_sync.py` and `tests/test_codex_room.py`; see the [runtime guide](docs/setup/codex-runtime.md).
- ACP child-exit handling was a reported limitation: `setup/role-agent` forwards stdin until EOF,
  so a backend that exits early may surface only on the next input. Not re-reproduced; reproduce
  against current code before relying on it.
