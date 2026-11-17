# SETUP — Pi and OMP Peer seats

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

The OMP native tool `task` is present in `omp-peer`; it is not Paseo MCP and the role prompt forbids its use for
delegation.
