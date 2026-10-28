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

The shared [role contract](agents/contract/COMMON.md) is prepended to each role's own prompt
by the launchers, resolved from the kit rather than the session directory. Missing/unreadable
sources or a combined prompt over 16 KiB block launch; a Markdown link is not the loader.

Backends: **Claude, Codex, Devin, Copilot, Cursor, Pi, Amp, Kiro, Droid, Antigravity**. Codex loads prompts with
`model_instructions_file`. Claude adds the role to `appendSystemPrompt` in the SDK
`initialize` message when using stream-json, or uses `--append-system-prompt` outside the SDK.
Pi uses native launch instructions. Devin/Copilot/Cursor/Amp/Kiro/Droid/Antigravity use the ACP proxy, which adds role
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
runtime state.
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
| Handoff | Peer ends its turn with the six-cell [handoff](agents/PEER.md#handoff--always-return); Lead reads it from the `finished` notification ([Lead monitoring](agents/LEAD.md#monitoring)) |
| Review | Lead reads the exact candidate and evidence; complex/review tasks use the [Dual-Lane review skill](.agents/skills/dual-lane-review/SKILL.md) |
| Rework | Same Peer, one next-round assignment after a validated handback ([Lead acceptance](agents/LEAD.md#acceptance)); `REOPEN_REQUEST`/`DEPENDENCY_REQUEST` follow [handling-reopen](.agents/skills/handling-reopen/SKILL.md) |
| Intervention | Supervisor acts only on an event and tells the owning Lead ([Supervisor](agents/SUPERVISOR.md#intervening-on-events)) |
| Loops / reset | Counted in events, never time; reset needs Human confirmation ([context-reset](.agents/skills/context-reset/SKILL.md), [rework-escalation](.agents/skills/rework-escalation/SKILL.md)) |
| Acceptance | Lead decides; Supervisor does not decide in their place |
| Archiving | Supervisor archives the Lead when the Human confirms the project is closed |

This table summarizes the role contracts; the [common contract](agents/contract/COMMON.md) and the
role prompts own the rules (candidate identity, cessation gate, event-driven work). The project's
`WORKSPACE_PROTOCOL.md` owns Human-authorized provider/profile selection
(see the [Routing template](examples/WORKSPACE_PROTOCOL.md#routing)). There is no coordination desk,
registry, ledger, patrol, timer, recurring schedule, or heartbeat.

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
- Peers do not see decision provenance. `ALREADY DECIDED` carries reasons and evidence, never who
  decided, so authority cannot bias the Peer. The cost: a Peer cannot tell whether a
  `REOPEN_REQUEST` is cheap (Lead-owned) or needs a Human decision; the Lead resolves that with
  [handling-reopen](.agents/skills/handling-reopen/SKILL.md), and the Human sees provenance through
  the Review gate and the acceptance summary. Adding `Who may reopen` to the brief would reveal
  the source: that is a trade-off change for the Human to decide, not a fix.

- Paseo is the sole agent control plane and owns lifecycle and topology. Inspect live state before
  operating. Paseo >= 0.13.0 is required: earlier daemons could lose finish notifications across a
  restart, which the no-polling rule cannot recover from. Verified live on 0.13.0: a `finished`
  notification queued before a daemon restart is still delivered to the Lead afterwards; a Peer cut
  mid-turn by the restart yields `was closed`, not `finished`, and its round must be reassigned;
  archived agents stay out of `list_agents`. A `send_agent_prompt` receipt only proves the prompt
  was queued.
- Connected hosts (`paseo host add`) are opt-in per repository in `WORKSPACE_PROTOCOL.md` § Routing;
  the kit has not been verified live with a remote Peer.
- `setup/codex-room` preserves private runtime data and canonical config, disables native
  multi-agent features, and rejects ambiguous or symlinked runtimes. These contracts are covered by
  `tests/test_codex_room_runtime.py` and `tests/test_codex_room.py`; see the [runtime guide](docs/setup/codex-runtime.md).
- Codex Peer sandbox: `codex-peer` profiles must set `modeId: auto-review`; that mode keeps `.git` read-only,
  so a committed candidate needs Human-authorized `full-access`. Details and measurement:
  [Peer sandbox and worktrees](docs/setup/codex-runtime.md#peer-sandbox-and-worktrees).
- ACP child-exit limitation: `setup/role-agent` forwards stdin until EOF, so a backend that exits
  early may surface only on the next input.
