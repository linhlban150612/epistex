# Context compaction

Aim: compact near 100k tokens without changing role prompts or canonical Codex configuration.
Project settings apply when the seat's CWD is this checkout; seat env applies to every launch
of that role provider, so use these providers only for Epistex. Reload providers and launch new
sessions after installation. Static checks do not prove a live compaction; launch probes remain
with the Lead.

| Agent (verified version) | Mechanism | Scope | Effective threshold | Status |
|---|---|---|---|---|
| Codex 0.161.0, all roles | `model_auto_compact_token_limit=100000` in generated room TOML | Project/role runtime only | 100,000 | Configured in sync; CLI update blocked by the no-`~/.codex`-writes constraint |
| Claude 2.1.294, all enabled Claude seats (Supervisor, Lead, Peer) | `CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000` | Epistex role-provider env | 100k window; backend buffer may trigger earlier | Configured in example for Peer/Supervisor and applied live on all three Claude seats; Paseo launch probe on 2.1.294 showed the env value `100000` in the Claude process |
| Pi 1.1.0, Peer | `.pi/settings.json`, per-model `reserveTokens` | Checkout | 100,000 for the five sourced pins below | Configured; Haiku window unknown — skipped (default compaction) |
| OMP 18.8.4, Peer | `.omp/config.yml`, `compaction.enabled=true`, `thresholdTokens=100000` | Checkout | 100,000 (clamped below model window) | Configured; use `/home/linhlb/.bun/bin/omp`, not stale `~/.local/bin/omp` |
| Copilot 1.0.93, Peer | No verified threshold variable in installed binary/help | — | Backend default | Not configurable through inspected surfaces |
| Amp 0.0.1791432144, Supervisor/Lead/Peer | No exposed threshold in settings reference | — | Backend default | Not configurable through the inspected CLI schema/help |
| Cursor Agent 2026.10.01-e373342, Peer | No exposed threshold in help/bundled JS search | — | Backend default | Not configurable through the inspected local surfaces |
| Devin 3000.11.3, Supervisor/Peer | `agent.compaction_threshold_tokens=100000` in `~/.config/devin/config.json` | User-wide, **not workspace-scoped** | 100,000 | Applied user-wide (Human opt-in); existing file left untouched |
| Kiro 2.30 (kiro-cli acp v2), Supervisor/Lead/Peer | No exposed compaction threshold in `setup/kiro-*.json` agent schema | — | Backend default | Not configurable through the seat-owned agent JSON |
| Factory Droid 0.241.1, Lead/Peer | No exposed threshold in `droid exec --help` / ACP surface | — | Backend default | Not configurable through the inspected CLI help |
| Antigravity (agy_acp_server.par), Lead/Peer | No exposed threshold in probed session/new result | — | Backend default | Not configurable through the probed ACP surface |
| GLM (glm-acp-agent), no seat installed | Not installed on this machine | — | Unknown | Blocked: binary not installed; no evidence gathered |

## Installed evidence

- Codex: `strings $(command -v codex)` contains `model_auto_compact_token_limit`.
- Claude: the installed binary contains `CLAUDE_CODE_AUTO_COMPACT_WINDOW`. In
  stream-json `Popen` inherits the
  process environment; non-stream uses `os.execvp`. No launcher change needed. `claude-lead` is present in the example.
- Pi package root: `~/.pi/agent/install/releases/1.1.0/node_modules/@earendil-works/`.
  `pi-coding-agent/dist/core/settings-manager.js` loads project settings and
  resolves overrides by exact `provider/modelId`; `dist/core/compaction/compaction.js`
  triggers above `contextWindow - reserveTokens`. `keepRecentTokens` stays at its default.
- OMP package root: `~/.bun/install/global/node_modules/@oh-my-pi/` (18.8.4).
  `pi-coding-agent/src/session/context-settings.ts` registers the fixed threshold;
  `src/config/settings.ts` reads project `config.yml`;
  `pi-utils/src/dirs.ts` identifies the project directory as `.omp`.
- Copilot: `rg -a`, `strings`, `strings -el` of `~/.local/bin/copilot`, and `copilot help`
  found no proposed variable.
- Amp: `amp --help` settings reference has no compact/threshold option.
  `amp threads --help` also lacks `compact`; do not assume `amp threads compact` exists.
- Cursor: `cursor-agent --help` has no compact/threshold option; searching all 80 bundled
  JS files for `autoCompact|auto_compact|compactionThreshold|compaction_threshold` finds no matches.
- Devin bundled docs under `~/.local/share/devin/cli/_versions/3000.11.3/share/devin/docs/`:
  `reference/configuration/config-file.mdx` makes `agent` user-only;
  `changelog/stable.mdx` documents the token knob. `devin acp --help` has no compaction env
  override. Existing value: `100000`.
  `devin doctor --json` returns `ok: true` without a config error. The checker only prints an
  informational note if this user-wide value is absent/different; it never fails on it.

## Model windows

Source: local `~/.pi/agent/models-store.json`, exact IDs under `openrouter.models` or
`github-copilot.models`. The generated Pi catalog has no exact Haiku 5.5 entry either.
No sourced Pi window is ≤100k; a future such pin must be skipped rather than get a negative reserve.

| Pi pin | Context window | reserveTokens |
|---|---:|---:|
| `openrouter/deepseek/deepseek-v4.1-flash` | 1,048,576 | 948,576 |
| `github-copilot/gpt-6-luna` | 1,000,000 | 900,000 |
| `openrouter/moonshotai/kimi-k3` | 1,048,576 | 948,576 |
| `openrouter/z-ai/glm-5.3-flash` | 1,048,575 | 948,575 |
| `openrouter/z-ai/glm-5.3` | 1,048,576 | 948,576 |
| `openrouter/anthropic/claude-haiku-5.5` | Window unknown | Skipped (default compaction) |
