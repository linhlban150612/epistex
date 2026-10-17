# Epistex — standalone agent roles on Paseo

Epistex provides role prompts and launchers for Supervisor, Lead, and Peer seats across the
backends listed below, with Paseo as the sole control plane.

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
are in [docs/setup/](docs/setup/), including [Antigravity](docs/setup/antigravity.md) and [Factory Droid](docs/setup/droid.md).

## Paseo-only workflow

Supervisor observes through Paseo and acts only on events; the Lead owns coordination structure,
routing, review, and acceptance. The Peer is the sole writer; there is no dedicated Reviewer agent.
Supervisor opens a Lead in the project workspace and does not create a Peer.

| Step | Coordination mechanism / owner |
|---|---|
| Discovery | Supervisor uses Paseo `list_workspaces`, `list_agents`, `list_providers`, `list_models` |
| Assignment | Supervisor opens a Human-authorized Lead with `create_agent(workspaceId=...)`; passes the Supervisor agentId in `initialPrompt` |
| Implementation | Lead defines scope and creates a Peer through Paseo; Peer is the sole writer |
| Handoff | Peer returns all six items in its session; the handoff is its last message. Lead reads only that message from the Paseo finish notification (`<agent-response>`; if truncated, `paseo agent logs <id> --filter assistant_message --tail 1`) for done / not done and candidate identification details, not the Peer timeline |
| Review | Lead reads the exact candidate and evidence. Complex/review tasks use the [Dual-Lane review skill](.agents/skills/dual-lane-review/SKILL.md) (two Peers from different model families). Existing Human review and agent-creation gates apply |
| Rework | Lead sends exactly one `send_agent_prompt` specifying task, round, feedback, baseline and rejected candidate identities (commit or frozen snapshot/diff); preserves both. See [Peer handoff](agents/PEER.md#handoff--always-return) and [Lead acceptance](agents/LEAD.md#acceptance) |
| Intervention | Only on an event (notification, Lead question, Human request), Supervisor may use `list_pending_permissions`, `respond_to_permission`, `cancel_agent`, `set_agent_mode`, then tells the owning Lead |
| Loops / reset | Loops are counted in events, never time. Lead proposes reset from the same baseline and last frozen candidate identities (baseline if none), preserving frozen artifacts and authority. Human confirmation through Supervisor (directly if none) is required before stopping/archiving the old agent; confirm it can no longer write before replacement. See [Lead monitoring](agents/LEAD.md#monitoring) and [Supervisor reset](agents/SUPERVISOR.md#loops-and-context-reset) |
| Acceptance | Lead decides; Supervisor does not decide in their place |
| Archiving | Supervisor archives the Lead when the Human confirms the project is closed |

These are summaries of the role contracts, not a second policy source; only the Human changes
these contracts. [Ownership](agents/LEAD.md#ownership) identifies commits by base/candidate SHA,
branch and worktree; without commit permission, Git or a base commit, use deterministic
baseline/candidate snapshots/diffs, each with checksum and path. Agree the baseline before writing,
keep it across rework/reset, and preserve prior frozen candidates; SHA checks apply only to commits.
The project's `WORKSPACE_PROTOCOL.md` owns Human-authorized provider/profile selection, family
evidence and fallback (see the [Routing template](examples/WORKSPACE_PROTOCOL.md#routing)). Unknown
family or no valid authorized pair means `BLOCKED`, never a one-lane downgrade or self-authorized
model/effort change.

There is no coordination desk, registry, ledger, patrol, timer, recurring schedule, or heartbeat.
Lead reads Peer responses from the Paseo finish notification, or from `paseo agent logs` when it is truncated;
idle/notification status does not prove that work is complete.

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
python3 -c 'compile(open("setup/codex-room").read(), "setup/codex-room", "exec")'
bash -n setup/setup-seats.sh
git diff --check
```

Tests use fixtures and temporary config/state; they do not replace auth, model, backend launch,
actual CWD, or live recovery checks.

### Cautions and known limitations

- Context compaction is backend-dependent; some seats remain unconfigured and Devin is user-wide,
  not workspace-scoped. See [context compaction](docs/setup/context-compaction.md).

- All roles run as the same Unix user; scope and tool visibility are not an OS sandbox (see above).
- Paseo is the sole agent control plane and owns lifecycle and topology. Inspect live state before
  operating.
- `setup/codex-room` preserves private runtime data and canonical config, disables native
  multi-agent features, and rejects ambiguous or symlinked runtimes. These contracts are covered by
  `tests/test_codex_room_runtime.py` and `tests/test_codex_room.py`; see the [runtime guide](docs/setup/codex-runtime.md).
- ACP child-exit limitation: `setup/role-agent` forwards stdin until EOF, so a backend that exits
  early may surface only on the next input.
