# SETUP — Pi Peer and OMP seats

Use the backup, merge, protocol, reload and live verification steps in
[SETUP.md](../../SETUP.md). Before configuration, check the `pi` and `omp` executables,
backend auth and discovery with `paseo provider models pi --json` and
`paseo provider models omp --json`.
Do not print credentials to check auth.

Merge into `.agents.providers` and keep existing providers and state unchanged:

| Field | `pi-peer` | `omp-peer` |
|---|---|---|
| `extends` | `pi` | `omp` |
| `command` | `["<KIT>/setup/role-agent", "peer", "pi"]` | `["<KIT>/setup/role-agent", "peer", "omp"]` |
| `enabled` | `true` | `true` |
| `env` | `{}` | `{}` |
| `paseoTools.enabled` | `true`, Peer deny-list (every catalog tool blocked; [SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)) | same as `pi-peer` |
| `models[0].id` | `huggingface/deepseek-ai/DeepSeek-V4.1-Flash-1017` | `huggingface/deepseek-ai/DeepSeek-V4.1-Flash-1017` |
| `models[0].isDefault` | `true` | `true` |
| `models[0].thinkingOptions` | `[{"id":"low","label":"Low","isDefault":true}]` | same as `pi-peer` |

The default effort of both seats is `low` to reduce cost (`medium`/`high` can still be selected manually through a profile);
`setup-seats.sh --check` checks this default. Check discovery again before another installation. Replace `<KIT>` with the absolute path, keep the launcher
executable, run `paseo reload` and create a new session with the model/effort and mode from discovery.
When you run from the CLI, pass `--thinking low` to use the profile effort.
A live check showed that a command without an effort can run at `high`, even when the profile sets `low`.
Pi uses the native repeatable `--append-system-prompt`. OMP uses only the last value, so the
launcher merges all caller `--append-system-prompt` values (text or files that OMP can read)
with the role content before it calls OMP. Other RPC args and stdin stay unchanged. The launcher keeps
the existing CWD and auth home; these two backends do not use the ACP proxy.

Check a live session: the heading from active instructions must be `# Peer — independent co-worker`,
`pwd` must be the correct workspace, model/effort must be correct and the inventory must have no Paseo tools, including deferred
discovery if present. Do not read the role file as a substitute for injection evidence. Diagnostics do not replace a
live launch.

Every `omp-peer` profile has `modeId: full` (Full Access; Write Approval and Always Ask stop a non-interactive Peer at a permission request);
`--check` requires it. `pi-peer` has no mode.

Each seat has 12 profiles. Profile model pins (profile effort options are `low` except where indicated):

| Seat | Model IDs | Effort pins |
|---|---|---|
| `pi-peer` | `huggingface/deepseek-ai/DeepSeek-V4.1-Flash-1017`; `openrouter/deepseek/deepseek-v4.1-flash-1017`; `openai-codex/gpt-6-luna`; `openrouter/moonshotai/kimi-k3`; `openrouter/z-ai/glm-5.3-flash`; `openrouter/z-ai/glm-5.3`; `openrouter/anthropic/claude-haiku-5.5`; `xai/grok-4.7` | low; GPT-6 Luna, Haiku and Grok 4.7 also medium; GLM-5.3 also high |
| `omp-peer` | Same list as `pi-peer`, but Grok 4.7 is `xai-oauth/grok-4.7` | low; GPT-6 Luna, Haiku and Grok 4.7 also medium; GLM-5.3 also high |

Use `pi-peer`/`omp-peer` for coordination only when Human allows delegation. Do not delete sessions
or change credentials; role/MCP separation is not an OS sandbox.

Do not use `github-copilot/gpt-6-luna` (Copilot quota 429). Grok 4.7 uses xAI OAuth (`xai` in Pi, `xai-oauth` in OMP), not OpenRouter. OMP compaction still uses the fixed `thresholdTokens` in `.omp/config.yml`.

## OMP seats on Factory models

`omp-supervisor`, `omp-lead`, `omp-peer-1`, `omp-peer-2` and `omp-peer-3` use the OMP provider `factory-droid`.
The OMP `factory-droid` catalog has no `gemini-4-*` (`Model "factory-droid/gemini-4-argon" not found`, also after
`omp models refresh factory-droid`); Droid 1.12.1 also no longer has this model. The model list is the same as the Droid seats
of the same role ([droid.md](droid.md)). The `omp-peer` seat above stays unchanged.

| Seat | `command` | Paseo tools | Model (`factory-droid/<id>`) | Default |
|---|---|---|---|---|
| `omp-supervisor` | `["<KIT>/setup/role-agent","supervisor","omp"]` | Supervisor tool set ([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)) | `claude-sonnet-5-5`, `claude-opus-5-5`, `gpt-6.1-sol`, `gemini-3.8-flash`; low/medium | `claude-sonnet-5-5`, low |
| `omp-lead` | `["<KIT>/setup/role-agent","lead","omp"]` | Lead tool set plus `epistex_assign` ([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)) | `claude-opus-5-5`, `claude-fable-5.1`, `gpt-6-astra`, `gpt-6.1-sol`, `claude-sonnet-5-5`; low/medium | `claude-opus-5-5`, low |
| `omp-peer-1`…`3` | `["<KIT>/setup/role-agent","peer","omp"]` | No Paseo tools; only the plugin tool `epistex_submit_handoff` | `claude-haiku-5-5`, `claude-sonnet-5-5`, `claude-opus-5-5`, `claude-fable-5.1`, `gpt-6-astra`, `gpt-6.1-sol`, `gpt-6.1-terra`, `gpt-6-luna`, `gemini-3.8-flash`: low/medium; `glm-5.3`, `kimi-k3`: low/high; `deepseek-v4.1-flash-1017`: low | `claude-haiku-5-5`, low |

Fable 5.1 requires a Factory account with data sharing enabled for the publisher `anthropic`; otherwise the prompt stops with
`PERMISSION_DENIED` ("Access to this model requires data sharing to be enabled for publisher 'anthropic'").

Every seat has `extends: "omp"`; every profile has `modeId: full`. The Lead and Supervisor deny-lists follow
[SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor). Paseo connects MCP to OMP through its own
bridge, so Paseo tools appear as normal OMP tools. For each enabled seat, `setup-seats.sh --check` checks the launcher, the tools,
env, model/effort and that all profiles exist.

**Separate login for each seat.** The OMP provider `factory-droid` uses the login stored in the OMP profile. It does not
read an API key from env. The seat `env` is `{}` (the default login in `~/.omp/agent`, shared) or exactly one
`OMP_PROFILE` (the profile name, unique for each seat). To separate logins: run `omp --profile <name>`, log in to
Factory with `/login` (or `omp --profile <name> login factory-droid`), then set `"env": {"OMP_PROFILE": "<name>"}`
for the seat, run `paseo reload` and do a test launch. Check that new sessions are in `~/.omp/profiles/<name>/agent/sessions`,
not in `~/.omp/agent/sessions`. Use a different Factory account for each profile if you need a separate quota.
Do not use the existing profile names `omp-lead` or `omp-peer`: their `AGENTS.md` can point to a different prompt.
A new profile has no `config.yml`, extensions or memory from `~/.omp/agent`; an old seat agent stores its sessions
in `~/.omp/agent`, so create a new agent after you change `OMP_PROFILE`.

Live status (2026-11-15, OMP 18.20.2): all five seats run with `OMP_PROFILE` `epistex-<seat>`
(`epistex-omp-lead`, `epistex-omp-supervisor`, `epistex-omp-peer-1`…`3`), each profile with a different Factory
account. Each seat is in mode `full` with the default model at low, receives the correct role heading and CWD and writes sessions to
its own profile. `omp-supervisor` sees the Supervisor Paseo tool set and `omp-lead` sees the Lead Paseo tool set plus `epistex_assign` ([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor));
`omp-peer-1`…`3` have no Paseo tools. Other models, one launch per seat at low: `omp-lead` `gpt-6-astra`,
`omp-supervisor` `gemini-3.8-flash` and `omp-peer-1`…`3` `gpt-6-astra`, `gpt-6.1-terra`, `gpt-6-luna` receive the
correct role heading; `claude-fable-5.1` runs on `omp-peer-1` and `omp-peer-2` and gets `PERMISSION_DENIED` on
`omp-lead` and `omp-peer-3` (the account does not have data sharing enabled for `anthropic`).

On the default login (2026-11-14, OMP 18.20.0, Paseo 0.15.4), `omp-supervisor` and `omp-lead` call `list_workspaces`
without a permission prompt. The OMP native tool `task` is still present in every OMP seat; it is not Paseo MCP and the role prompt forbids
its use for delegation.
