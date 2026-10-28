# SETUP — Paseo role seats

Common entry point: steps 1–8 install the two Codex seats (Lead/Peer) and check a real launch. Each
other backend reuses these common steps, then follows its own file:

For project/runtime selection and prerequisites, see the [Codex runtime guide](docs/setup/codex-runtime.md)
(steps 1–2).

| Backend | Guide |
|---|---|
| Claude Lead/Peer | [docs/setup/claude.md](docs/setup/claude.md) |
| Amp Supervisor/Lead/Peer through ACP | [docs/setup/amp.md](docs/setup/amp.md) |
| Kiro Supervisor/Lead/Peer through ACP (CLI V3 engine, confirmed model/effort config options, Lead accepts only the Paseo MCP loopback, no native subagents) | [docs/setup/kiro.md](docs/setup/kiro.md) |
| Antigravity Lead/Peer through ACP (modeId auto_edit/yolo) | [docs/setup/antigravity.md](docs/setup/antigravity.md) |
| Factory Droid Lead/Peer through ACP | [docs/setup/droid.md](docs/setup/droid.md) |
| Pi Peer, OMP Peer | [docs/setup/pi-omp.md](docs/setup/pi-omp.md) |
| Devin Peer through ACP | [docs/setup/devin.md](docs/setup/devin.md) |
| GitHub Copilot Peer through ACP | [docs/setup/copilot.md](docs/setup/copilot.md) |
| Cursor Peer through ACP | [docs/setup/cursor.md](docs/setup/cursor.md) |

Context compaction and limits for each backend: [context-compaction.md](docs/setup/context-compaction.md).

## 1. Put the kit and project at stable paths

Put the kit and the project at absolute, stable paths. The Paseo daemon must run as the same user. For
project root and runtime details, see [Codex runtime](docs/setup/codex-runtime.md#project-paths-and-runtime-prerequisites).

## 2. Check prerequisites

Confirm Bash, Python 3.11+, `jq`, Codex and the Paseo daemon. Check credentials and backends with
[prerequisite and compatibility details](docs/setup/codex-runtime.md#project-paths-and-runtime-prerequisites).

## 3. Enable Paseo tools injection

In `~/.paseo/config.json`, make sure:

```json
{"daemon":{"mcp":{"enabled":true,"injectIntoAgents":true}}}
```

Permissions by role live in the provider: Lead sets `paseoTools.enabled=true`, Peer sets `false`. Do not
use `injectIntoProviders`; that field is not the current provider policy mechanism.

### Paseo tools policy for Lead and Supervisor

Lead uses `paseoTools.disabledTools` to block the catalog and keeps exactly 11 tools:
`list_workspaces`, `list_providers`, `list_models`, `list_profiles`, `create_agent`, `send_agent_prompt`,
`cancel_agent`, `archive_agent`,
`list_pending_permissions`, `respond_to_permission`, `set_agent_mode`. Supervisor also keeps `create_workspace`, `get_agent_activity`, `get_agent_status` and `list_agents` (15 tools kept; 46 blocked), while Lead keeps 11 tools (50 blocked). Lead does not have `get_agent_activity`, `get_agent_status` and `list_agents`, so Lead waits for notifications instead of polling or reading the Peer timeline. Kiro Supervisor/Lead and Droid Lead use the same policy.
Lead runs without approval waits: Lead profiles use a bypass mode (`claude-lead` `bypassPermissions`, `agy-lead` `yolo`, `droid-lead` `auto-high`, `codex-lead` `full-access`: approval `never`, sandbox `danger-full-access`); `kiro-lead` auto-approves through agent `permissions.rules` (V3). `amp-lead` uses `local`: amp-acp has no bypass mode.
Codex Peer profiles use `modeId: auto-review` (writable workspace sandbox, no approval waits). The provider default `auto` leaves a non-interactive Peer in a read-only sandbox: file writes and `./verify` fail with `Read-only file system`. `setup-seats.sh --check` rejects `codex-peer` profiles without `auto-review`.
Groups blocked for Lead: 11 schedule/heartbeat, 22 browser, 5 terminal, 12 workspace/agent/provider;
for Supervisor the workspace/agent/provider group is down to 8 (see the list in the
[provider example](examples/paseo-providers.json)). Paseo >= 0.13.0 is required (reason: [known limitations](README.md#cautions-and-known-limitations)); the daemon and CLI must be the same version.
`speak` cannot be blocked and is outside the catalog. A test pins the 61-name catalog to force a review
when Paseo is upgraded. The `--check` script confirms the exact deny-list on every enabled provider.

## 4. Merge provider seats

Back up the config, then merge `agents.providers` and `daemon.agentProfiles` from `examples/paseo-providers.json`
into the matching sections of the existing Paseo file, selecting only the profiles for seats you enable.
The example is a backend catalog, not an instruction to enable every backend or overwrite an existing
`enabled: false`. Keep disabled provider definitions and session state; remove their profiles from the
operational `daemon.agentProfiles` list. Do not replace the whole file: keep other providers and the daemon configuration. Before
merging: replace `<KIT>` with the absolute path to `epistex`; if you need to pin the project, add an absolute
`env.EPISTEX_PROJECT_ROOT`; delete `_doc`; confirm model IDs with
`paseo provider diagnostic codex --json` or provider discovery. The example selects Lead `gpt-6.1-sol` and
Peer `gpt-6-luna`, default effort `low`. `command` must keep the correct role, `lead` or `peer`.

## 5. Paseo agent profiles

`examples/paseo-providers.json` holds the full backend catalog under `daemon.agentProfiles`; the live
config holds the operational subset. Being enabled is necessary, not project authorization: use the
Human-authorized provider/profile choices in the project's `WORKSPACE_PROTOCOL.md`. Lead must not
automatically create a Peer on its own backend provider, even through a different role-seat ID.
Use an authorized alternative or report `BLOCKED`; only Human can grant a same-provider exception.
Different providers do not guarantee independent quotas.

IDs use the pattern `<seat>--<model-slug>--<thinking>` where applicable; profiles contain no role prompt.
Lead/Supervisor read `list_profiles` notes before selecting. Notes describe role responsibilities,
not measured cost or speed: Supervisor observes and supports Human without implementing, assigning
Peers or accepting candidates; Lead coordinates, reviews and accepts; Peer implements, verifies and
hands off evidence. Effort and model names do not establish price or latency.

Follow the [MCP reference](https://paseo.sh/docs/mcp.md) when materializing a profile:

| Profile field | `create_agent` field |
|---|---|
| `provider` + `model` | `provider` as `provider/model` |
| `modeId` | `settings.modeId` |
| `thinkingOptionId` | `settings.thinkingOptionId` |
| `featureValues` | `settings.features` |

Omit absent optional settings. If model is absent, discover an available model with `list_models`
before launching; never guess. Only use feature IDs discovered from `inspect_provider`. Supply the
task in `initialPrompt`, not in profile notes. Amp profiles omit thinking when the model has no options;
some ACP models encode effort in the model ID rather than `thinkingOptionId`.

To normalize Epistex notes and remove profiles for explicitly disabled Epistex seats, back up the
config outside Git, generate a candidate, inspect its diff, then install it:

```bash
jq --argjson catalog false -f <KIT>/setup/normalize-profiles.jq <CONFIG> > <CANDIDATE>
```

The filter preserves provider definitions, launch settings and non-Epistex profiles. Use
`--argjson catalog true` when maintaining the example catalog so disabled backend profiles stay there.
It does not authorize profiles or choose models. Validate the candidate with
`PASEO_CONFIG=<CANDIDATE> bash <KIT>/setup/setup-seats.sh --check`.
After installing, run `paseo reload`, then verify with a new session or a separate launch; reload
output alone does not prove model, settings or role. Existing sessions retain their launch catalog.

## 6. Set the contract and protocol in the target project

- Use `examples/AGENTS_MD_SNIPPET.md` to add the common contract that both Lead and Peer read.
- For Java/Spring Boot repositories, copy `examples/target-repo/verify` and `examples/target-repo/paseo.json`
  (see `examples/target-repo/README.md`) so `quick`/`it`/`full` checks, port and DB per worktree are standard.
- Copy `examples/WORKSPACE_PROTOCOL.md` to `<PROJECT>/WORKSPACE_PROTOCOL.md`, then fill in the repo's own risk,
  authority, task class and review gate. This file is for Lead; Peer receives the necessary
  constraints through the task brief.

Before you commit the two files above, follow the target repo's hygiene rules. If the repo forbids persona/process
documents, keep `WORKSPACE_PROTOCOL.md` local and ignored (or in a location the Human manages), and let
`AGENTS.md` hold only product boundaries, invariants, canonical docs and durable verification.
Do not create an evidence folder, review packet or status ledger in Git. Do not put repo-specific
policy into a Paseo provider or the Peer prompt.

## 7. Build and check

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s <KIT>/tests
bash <KIT>/setup/setup-seats.sh
paseo reload
bash <KIT>/setup/setup-seats.sh --check
```

The script does not edit the global config; a run without `--check` only sets the executable bit (chmod is needed),
and the runtime is prepared when Paseo starts the seat. `--check` fails if the config/provider is missing or has a
wrong model, effort or tool permission; it needs Bash, jq, Python 3.11+, dirname, wc, grep and
`${CODEX_BIN:-codex}`, and does not need Paseo on PATH. `PASEO_HOME`/`PASEO_CONFIG` select a config at a non-default
location; if you use `CODEX_BIN`, set the same value for the checker and the providers. A passing result
does not prove auth, the daemon, model availability or a successful launch: those are steps 2 and 8.

## 8. Prove isolation

Start a `codex-peer` agent and ask it to report the common and role headings from its received
instructions (without reading source files): `# Common contract — Supervisor, Lead and Peer`
and `# Peer — independent co-worker`. Repeat with `codex-lead` and its `# Lead` heading.
Some models do not reliably quote received instructions. A `MISSING` reply alone is not
proof of missing injection: inspect the native session's recorded `base_instructions`
and ask behavioral questions about failure limits, non-Git candidate identities and
writer cessation. Do not put the expected answers in the smoke prompt.
Also check `find ~/.codex-runtime/epistex -maxdepth 3 -name config.toml`.

The two roles must have separate runtimes. `auth.json`, `skills` and `plugins` are symlinks; `config.toml` is a
separate generated copy that holds `model_instructions_file` pointing to runtime `role-instructions.md`
(common contract + role prompt), with `[agents].enabled`,
`[features].multi_agent` and `[features].multi_agent_v2` all `false`: Paseo is the only owner of
topology. Invalid TOML or a wrong policy table type makes the launch fail before the runtime changes.
The generated copy uses inline tables and keeps no comments or formatting, but keeps values outside the policy unchanged (including
multi-line strings); the canonical file is not modified. Sync does not delete private state and rejects a runtime or
parent directory that is a symlink. Each config/prompt replacement is atomic, not the entire sync;
an I/O error or concurrent change can leave partial updates
(details: [Codex runtime and resume](docs/setup/codex-runtime.md#codex-runtime-and-resume)).

This separates state and MCP permissions. It is not a sandbox against a malicious agent: the roles run as the same Unix
user, share skills/plugins and still have a shell. The Peer prompt forbids calling Paseo; hiding the Paseo MCP
does not absolutely stop a shell from calling the CLI.

## ACP proxy seats

Common part for Devin, Copilot and Cursor ([devin.md](docs/setup/devin.md),
[copilot.md](docs/setup/copilot.md), [cursor.md](docs/setup/cursor.md)).

- **Merge:** back up, then merge into `.agents.providers`. Do not replace the original backend or its
  credential/config home.
- **MCP:** keep injection enabled in the daemon (§3). These seats are Peers: `paseoTools.enabled=false`.
- **Schema entry:** `extends: "acp"`, `enabled: true`, `env: {}`, `command` of the form
  `["<KIT>/setup/role-agent","peer","<backend>"]`; `models: [{"id":"<MODEL>","label":"<LABEL>","isDefault":true}]`,
  add `thinkingOptions: [{"id":"<EFFORT>","label":"<LABEL>","isDefault":true}]` when the backend has effort.
- **Inject prompt:** `role-agent` switches to `setup/<backend>-acp` with `os.execv`; the launcher uses an
  ACP proxy that adds role instructions to the first prompt of each session, not to the system prompt.
  Do not add project policy to a provider or edit the backend's global instructions.
- **Live verify:** after `paseo reload`, create a new session with the real model/effort and mode from discovery.
  Check the role heading from the context the agent actually receives, the CWD with `pwd`, the model/effort and the inventory,
  including deferred discovery; a Peer must not see Paseo tools. Do not enable delegation in a smoke test.
  A native backend tool/subagent is not the same as Paseo MCP; role/tool visibility is not
  an OS sandbox. The Codex checker and diagnostics do not replace live verification.

## 9. Operations

Lead always creates a Peer with the role provider (`codex-peer` or a `*-peer` provider in `docs/setup/`);
never the original backend provider. Pass `modeId` and `thinkingOptionId` explicitly when you create an agent. A running
agent does not pick up provider changes; after you edit `~/.paseo/config.json`, run `paseo reload` and
create a new session. Common + role instructions have a combined ceiling of 16 KiB, checked
by setup and launchers; after an edit, run `setup-seats.sh --check` again.
