# SETUP — Kiro Lead and Peer through ACP

`kiro-peer` uses `role-agent peer kiro`, `kiro-lead` uses `role-agent lead kiro`; both
go through the local adapter `setup/kiro-acp <role>`; do not change the
Paseo package or global Kiro settings. You need a logged-in Kiro CLI, Python 3.11+,
and the kit at an absolute path. The adapter launches only **engine V3**
(`kiro-cli acp --agent-engine=v3 --auth-method=cli`); verified with CLI 2.33.1 to 3.2.1.
The `kiro` entry of the ACP registry (pin 3.0.0) uses `acp --agent-engine=v3`; `--auth-method=cli` is the default value, and the adapter sets it explicitly.
Do not infer the engine from the ACP protocol version: both v2 and v3 use version 1.

## Install runtime and provider

Keep credentials, sessions, settings and other agents unchanged. Install only the seat-owned file
`setup/kiro-peer.json` as `~/.kiro/agents/epistex_peer.json`; if that name already belongs to another
configuration, stop and ask Human for a decision; do not overwrite. Do not use a symlink.
`cp -n` does not overwrite: if the file exists but differs from the kit copy, replace it with the kit copy; `--check` requires
the installed file to match the kit file byte for byte.

```bash
mkdir -p ~/.kiro/agents
cp -n <KIT>/setup/kiro-peer.json ~/.kiro/agents/epistex_peer.json
kiro-cli agent validate --path ~/.kiro/agents/epistex_peer.json
```

Merge **only** `agents.providers.kiro-peer` and the four `daemon.agentProfiles` with provider
`kiro-peer` from the [sample provider](../../examples/paseo-providers.json); replace `<KIT>` with the
kit path. Keep other providers unchanged. `extends=acp`; `paseoTools` is enabled with the Peer deny-list (every catalog tool blocked; [SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)).
Do not add an MCP server to Peer new/load.

| Model | Effort | Profile |
|---|---|---|
| `claude-opus-5.5` | `low` | `kiro-peer--claude-opus-5-5--low` |
| `claude-opus-5.5` | `medium` | `kiro-peer--claude-opus-5-5--medium` |
| `claude-sonnet-5.5` | `low` | `kiro-peer--claude-sonnet-5-5--low` |
| `claude-sonnet-5.5` | `medium` | `kiro-peer--claude-sonnet-5-5--medium` |

The default model of `kiro-peer` and `kiro-supervisor` is `claude-sonnet-5.5` (effort `low`) to reduce cost; `setup/kiro-peer.json` and
`setup/kiro-supervisor.json` set `model` to `claude-sonnet-5.5`, and `setup/kiro-lead.json` sets `claude-opus-5.5`: the adapter requires the initial session model to be in `MODELS`, so if this field is missing, launch fails with "Kiro restored an unsupported mode/model". Paseo still changes the model through the profile: V3 has no `session/set_model`, so the adapter returns `-32601` and Paseo uses `session/set_config_option` `configId=model`. `kiro-lead` keeps the default `claude-opus-5.5` in the seat config. Opus is still selected manually through a profile.

Supervisor copies `provider`, `model`, `thinkingOptionId` into `create_agent` and uses the project
workspace. Lead has no `create_agent`: Lead gives the profile id to `epistex_assign`, and this tool
copies those fields from the profile. Pass `modeId` explicitly with the fixed mode of the seat (`epistex_peer`, `epistex_lead`,
`epistex_supervisor`); every other mode switch is rejected. Paseo does not inherit the Lead mode
([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)), so every profile has the fixed mode of its seat: `kiro-peer` `epistex_peer`, `kiro-lead`
`epistex_lead`, `kiro-supervisor` `epistex_supervisor`; `setup-seats.sh --check` rejects other values.
After the merge, run `setup/setup-seats.sh` and the checker from [SETUP.md](../../SETUP.md), then
`paseo reload`, and create a new session. The static checker does not prove a live launch.

## Kiro Lead

`kiro-lead` installs only `setup/kiro-lead.json` as `~/.kiro/agents/epistex_lead.json` (exact
bytes, no symlink; if the name already belongs to another configuration, stop and ask Human), then merges **only**
`agents.providers.kiro-lead` and the four profiles `kiro-lead--claude-{opus,sonnet}-5-5--{low,medium}`
from the [sample provider](../../examples/paseo-providers.json). Model/effort are the same as Peer (table above);
`low`/`medium` are choices in the `effortLevel` option that the backend returns, and the adapter confirms
`currentValue` as for Peer. The fixed mode is `epistex_lead`.

```bash
cp -n <KIT>/setup/kiro-lead.json ~/.kiro/agents/epistex_lead.json
kiro-cli agent validate --path ~/.kiro/agents/epistex_lead.json
```

Provider: `extends=acp`, command `["<KIT>/setup/role-agent","lead","kiro"]`,
`paseoTools.enabled=true` with the Lead deny-list from
[SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor); Paseo enforces that list on the server. The agent file allows only
the Peer native tags (`read`, `write`, `shell`, `web`) plus `@paseo/epistex_assign` (the [delivery plugin](delivery-plugin.md) tool, the only way for Lead to create a Peer; the adapter requires this tag like every other Paseo tag) and exactly 9 Lead tools in the form
`@paseo/<tool>`. There is no `allowedTools`/`toolsSettings`: permissions are in the agent `permissions.rules`
(allow `fs_read`, `fs_write`, `shell`, `web_fetch`, `web_search`; Lead adds `mcp` that matches exactly 10 (9 Paseo tools and `epistex_assign`)
`paseo/<tool>`), so Lead approves every tool itself (bypass) and Peer is not asked for permission on each call. Kiro
built-in policy (for example, blocking writes to Kiro's own settings) and denies in other scopes still win; other tools still
ask through an ACP permission request. There is no `knowledge`: V3 does not advertise this tool as a
tag, and it is still experimental. Enable it again only when V3 actually advertises `knowledge`; then add it back to
`tools` of all three files and check the related capability/permission, or Lead can be asked for permission.
`includeMcpJson=false`, `mcpServers={}`: MCP is not read from workspace or global config.

**Accepted MCP** on `session/new`, `session/load`, `session/resume`: `[]` or exactly one
server `{"type":"http","name":"paseo","url":…,"headers":…}` with exactly those four keys;
URL `http://<host>:<port>/mcp/agents?callerAgentId=<id>` with host `127.0.0.1`, `localhost`
or `::1`, with a port, no userinfo/fragment, and a query with only one non-empty `callerAgentId`;
`headers` is `[]` or exactly one `{"name":"Authorization","value":"Bearer <token>"}`.
`[]` is only for Paseo probe sessions (catalog/features/diagnostics send `mcpServers: []`);
a probe session can never run `session/prompt`, and
a real session needs exactly the Paseo server above. Everything else is rejected before the backend: no server or several
servers, stdio/sse, another name, extra keys, https, a non-loopback host, another path/query, another
header. `session/resume` runs the same MCP and CWD validator as load for both roles; a resumed
session replaces the old state, cancels pending confirmations and is not tracked, so prompts are still
refused. Peer still rejects every MCP server.

Kiro V3 advertises tools through `_kiro/tools/didChange` as **tags**: builtin categories (`read`, `write`,
`shell`, `web`) and `@paseo/<tool>` for MCP tools that the agent `tools` selects (live: `kill_agent`/`list_agents`, which the server also returns,
are still filtered out of the tags by Kiro). The adapter requires tags ⊆ `tools` of the agent file
and, for a session with Paseo, all `@paseo/<tool>` tags of every Paseo tool in the agent file (Lead: 8, Supervisor: 15). `_kiro/mcp/status` is a full snapshot; Kiro reports
`connected` **before** the `didChange` that carries the MCP tags, so the adapter waits for a `didChange` newer than the snapshot (at most
30 s) before it decides. An unknown tag (including `subagent`, bare `kill_agent`, `@paseo/<blocked tool>`, another
server) or a missing Paseo tool makes the session fail instead of exposing it. V3 loads MCP tools on demand: the model
sees only `tool_load`/`tool_call`, and the `tool_load` catalog contains only the tools selected in `tools`.
`speak` (live): the server registers `speak` only when voice tools are enabled, and then
`disabledTools` cannot block it; a normal launch has no `speak` in the Lead/Supervisor catalog. If
`@paseo/speak` appears as a tag, the seat fails closed; a change to the allowlist needs a Human decision.

Seat `kiro-supervisor`: `role-agent supervisor kiro`, `setup/kiro-supervisor.json`, installed agent `~/.kiro/agents/epistex_supervisor.json`, Supervisor Paseo tool policy (15 tools, [SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)). Live (CLI 3.1.0, Paseo 0.15.3): `kiro-supervisor` Sonnet/low calls `list_hosts` without a permission prompt. Live 2026-11-12 (Paseo 0.15.4): `kiro-supervisor` Sonnet/low sees exactly 15 Paseo tools.

## Model/effort through standard config options

V3 uses `session/set_config_option` with `configId=model` and `configId=effortLevel` (category
`thought_level`); `session/set_model`, `_kiro.dev/commands/*` and `/effort` no longer exist. The adapter lets through
only these two options, with values in `MODELS`/`EFFORTS`; `mode`, `autopilot`, `memoryReflection`,
`contentCollection` and unknown options are hidden from `configOptions` (in both the response and `config_option_update`) and
are rejected on set. Kiro returns success but **keeps the old value** when the value is not valid (live), so
the adapter returns success only when `currentValue` in the response equals the requested value; a selection that is not
confirmed makes the session lose its ready state, and prompts are refused. Backend errors keep their
code/message/data. After a model change, if the effort differs from the previous value, the adapter reapplies and confirms it
(live: Kiro does not reset it, but Paseo can skip the setter when thinkingOptionId does not change).

Do not launch with `--agent`, `--model`, `--effort` or `--trust-*`: V3 rejects those flags. The adapter
sends `_meta.kiro.modeId=epistex_<role>` on `session/new`; the initial model comes from the `model` field of the
agent JSON. The V3 default effort is `high` (Opus 5.5 returns `medium`): if it is not `low`/`medium`, the adapter
pins `low` and confirms it before it returns the response. Kiro can return `session/new` before the model catalog
finishes loading (no `model`/`effortLevel`); the adapter waits for a `config_option_update` with those two options. Load
keeps the saved mode/model/effort (verified live in a new process); a `config_option_update` or
`current_mode_update` that moves the session outside the allowed mode/model/effort revokes the session and sends
`session/cancel`.

The CLI keeps authentication (`--auth-method=cli`); the adapter does not answer `_kiro/auth/getAccessToken`.

## Native topology and role

The Peer seat uses a native tools allowlist plus exactly one tag `@paseo/epistex_submit_handoff` (the handoff tool of the [delivery plugin](delivery-plugin.md)); **there is no `subagent`, `goal` or Paseo catalog tool**. The adapter accepts exactly one injected Paseo server for every role, and rejects a Peer session with a Paseo channel that lacks this tag or has another Paseo tag. New/load
succeeds only after mode/model and the raw tool inventory are checked. Load discards the old inventory/session
validation, waits for a new advertisement and checks the inventory again just before a successful response;
an unsafe inventory that appears during confirmation makes the load fail. The installed runtime must
match the kit file byte for byte. A workspace `.kiro/agents/epistex_peer.json`/`.md` (including in an ancestor)
makes the launch/session fail, so that the workspace cannot override the global agent. Do not fix the override automatically.
Mode switches, native agent/chat/rewind commands, subagent lifecycle and global setting writes
are rejected. From the V3 extensions, the adapter relays only `_kiro/session/context` and `_kiro/session/compact`
(compact goes through the same prompt gate) when the backend advertises them, and advertises only these two methods again in
`initialize`; `_kiro/workflow/*`, memory, export, `_kiro/mcp/*`, `_session/*` (including `_session/steer`),
`session/fork`/`delete`/`list` are rejected with `-32601`. `session/close` is relayed. Approval still goes through an ACP
permission request with the agent's `options[]`; the adapter does not create consent itself. Notifications and unknown metadata are kept unchanged; unsupported agent-to-client requests
get a JSON-RPC error, and permission and negotiated fs/terminal callbacks are relayed normally.

Role instructions are prepended to the **first prompt of each new session** (`session/new`);
they are not a system prompt. A `session/load` session does not get them again because the history already has the role.
`session/prompt`, cancellation, errors and replay are not faked as completion. Shell and the same Unix user are still not an OS sandbox; the policy
does not stop a malicious agent from changing config files or calling the CLI itself.

## Independent verification

Do not send a model prompt in the metadata probe:

```bash
EPISTEX_REAL_KIRO_PROBE=1 PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_kiro_acp.py -v
```

The probe prints raw ACP through the Peer adapter: a new session in `epistex_peer` with the pinned effort, tags without
MCP/`subagent`, confirmation of all four selections, rejection of `mode`/`high`/`autopilot`/`session/set_mode`; then
load in the same process and in a new process, and a check that Sonnet/medium is unchanged. The fixture backend simulates
V3 behavior observed live (default `high`, an ignored value still returns success, tag inventory, catalog and MCP
that arrive late) and checks role/CWD, effort pin, ignored model/effort, model reset, hidden options/extensions,
cancellation, permission relay, unsafe inventory/mode in the middle of a session, override, backend rejection and
early exit. It does not replace live model smoke tests. Lead has no automatic probe yet: it was checked manually with
a loopback HTTP MCP that simulates Paseo (Paseo tags, model switch, probe load refuses prompt).

Lead launches the four profiles through Paseo after the frozen-candidate review; get the actual session/model/effort,
raw `config_option_update`, `_kiro/tools/didChange` and `_kiro/mcp/status`, or run the metadata probe on the same
candidate. In the live task prompt, ask the agent to describe the role heading **received in the session**,
list the tools it actually sees and print `pwd`; do not treat a reread of the prompt file as proof of injection.
Peer must receive `# Peer — independent co-worker`, the project CWD, no Paseo catalog tool or subagent; only `epistex_submit_handoff`.
Live status (CLI 2.33.1 to 3.1.0; 3.2.1: launch of `kiro-peer` Sonnet/low, role heading, CWD): the four `kiro-peer` profiles and `kiro-lead`/`kiro-supervisor`
Sonnet/low launch with the correct mode/model/effort, receive `# Common contract` plus the role heading, and the CWD is the project;
Peer has native tools and calls `epistex_submit_handoff`; the Lead catalog has 7 Lead tools plus `epistex_assign`, with no `speak`
and no `create_agent`; Lead calls `list_workspaces` without a permission prompt and creates `kiro-peer` through `epistex_assign`
([verification status](delivery-plugin.md#verification-status));
handback goes through the [delivery plugin](delivery-plugin.md), not through native notification. `session/cancel`,
`session/resume` and `session/load` through the Paseo lifecycle are not live-covered yet. Without a check through Paseo, conclude only that ACP metadata/fixture is verified; do not conclude that the seat is accepted.

Authoritative sources (running capabilities win over documentation examples):
[ACP](https://kiro.dev/docs/acp/), [V3 ACP migration](https://kiro.dev/docs/cli/v3/acp-migration/),
[V3 agent config](https://kiro.dev/docs/cli/v3/agent-config/),
[V3 permissions](https://kiro.dev/docs/cli/v3/permissions/), [built-in tools](https://kiro.dev/docs/tools/),
[custom agents](https://kiro.dev/docs/custom-agents/).
