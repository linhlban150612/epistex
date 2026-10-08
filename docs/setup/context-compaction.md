# Context compaction

Aim: compact near 100k tokens without changing role prompts or canonical Codex configuration.
Project settings apply when the seat's CWD is this checkout; seat env applies to every launch
of that role provider, so use these providers only for Epistex. Reload providers and launch new
sessions after installation. Static checks do not prove a live compaction; launch probes remain
with the Lead.

| Agent (verified version) | Mechanism | Scope | Effective threshold | Status |
|---|---|---|---|---|
| Codex 0.161.0, all roles | `model_auto_compact_token_limit=100000` in generated room TOML | Project/role runtime only | 100,000 | Configured in sync; CLI update blocked by the no-`~/.codex`-writes constraint |
| Claude 2.1.286, all enabled Claude seats + Peer | `CLAUDE_CODE_AUTO_COMPACT_WINDOW=100000` | Epistex role-provider env | 100k window; backend buffer may trigger earlier | Configured in example for Peer/Supervisor; live edit blocked by Peer seat policy |
| Pi 1.1.0, Peer | `.pi/settings.json`, per-model `reserveTokens` | Checkout | 100,000 for the five sourced pins below | Configured; Haiku window unknown — skipped (default compaction) |
| OMP 18.8.4, Peer | `.omp/config.yml`, `compaction.enabled=true`, `thresholdTokens=100000` | Checkout | 100,000 (clamped below model window) | Configured; use `/home/linhlb/.bun/bin/omp`, not stale `~/.local/bin/omp` |
| Copilot 1.0.93, Peer | Proposed `COPILOT_BACKGROUND_COMPACTION_THRESHOLD=0.5` | Would be role-provider env | Not applied | Blocked: no installed-binary/help evidence for this variable; no env or checker requirement added |
| Amp 0.0.1791432144, all roles | No exposed threshold in settings reference | — | Backend default | Not configurable through the inspected CLI schema/help |
| Cursor Agent 2026.10.01-e373342, Peer | No exposed threshold in help/bundled JS search | — | Backend default | Not configurable through the inspected local surfaces |
| Devin 3000.11.3, all roles | `agent.compaction_threshold_tokens=100000` in `~/.config/devin/config.json` | User-wide, **not workspace-scoped** | 100,000 | Applied user-wide (Human opt-in); existing file left untouched |

## Installed evidence

- Codex: `strings $(command -v codex)` contains `model_auto_compact_token_limit`.
- Claude: the installed binary contains `CLAUDE_CODE_AUTO_COMPACT_WINDOW`. In
  `setup/role-agent:83`, stream-json uses `Popen` without an `env` argument, inheriting the
  process environment; non-stream uses `os.execvp`. No launcher change needed. `claude-lead`
  is absent from the example; the checker covers it when enabled in an installed config.
- Pi package root: `~/.pi/agent/install/releases/1.1.0/node_modules/@earendil-works/`.
  `pi-coding-agent/dist/core/settings-manager.js:123–124,632–653` loads project settings and
  resolves overrides by exact `provider/modelId`; `dist/core/compaction/compaction.js:173–176`
  triggers above `contextWindow - reserveTokens`. `keepRecentTokens` stays at its default.
- OMP package root: `~/.bun/install/global/node_modules/@oh-my-pi/` (18.8.4).
  `pi-coding-agent/src/session/context-settings.ts:133–140` registers the fixed threshold;
  `src/config/settings.ts:2386–2444` reads project `config.yml`;
  `pi-utils/src/dirs.ts:623–625` identifies the project directory as `.omp`.
- Copilot: `rg -a`, `strings`, `strings -el` of `~/.local/bin/copilot`, and `copilot help`
  found no proposed variable. Older Zed bundles are not evidence for installed 1.0.93.
- Amp: `amp --help` settings reference has no compact/threshold option.
  `amp threads --help` also lacks `compact`; do not assume `amp threads compact` exists.
- Cursor: `cursor-agent --help` has no compact/threshold option; searching all 80 bundled
  JS files for `autoCompact|auto_compact|compactionThreshold|compaction_threshold` finds no matches.
- Devin bundled docs under `~/.local/share/devin/cli/_versions/3000.11.3/share/devin/docs/`:
  `reference/configuration/config-file.mdx:146–153` makes `agent` user-only;
  `changelog/stable.mdx:81` documents the token knob. `devin acp --help` has no compaction env
  override. Existing value: `100000`; mtime: `2026-10-05 11:05:27.994788747 +0700`.
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

Copilot windows below come from Pi's `github-copilot` catalog, not a Copilot CLI settings dump.
The 0.5 values are **hypothetical**, not configured or verified effective CLI thresholds.

| Copilot pin | Catalog window | Tokens at 0.5 (not applied) |
|---|---:|---:|
| `gemini-3.8-flash` | 1,000,000 | 500,000 |
| `kimi-k3` | 1,048,576 | 524,288 |
| `claude-haiku-5.5` | Window unknown | Unknown |
| `grok-4.7` | 500,000 | 250,000 |
| `claude-sonnet-5.5` | 1,000,000 | 500,000 |
