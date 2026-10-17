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
| OMP 18.8.4, Peer | `.omp/config.yml`, `compaction.enabled=true`, `thresholdTokens=100000` | Checkout | 100,000 (clamped below model window) | Configured; ensure the `omp` on Paseo's PATH is 18.8.4 or newer (`omp --version`) |
| Copilot 1.0.93, Peer | No verified threshold variable in installed binary/help | — | Backend default; no project setting | Re-checked 2026-10-17: `copilot --help` shows only `--context <tier>` (default/long_context), which is a window tier, not a threshold |
| Amp 0.0.1791432144, Supervisor/Lead/Peer | No exposed threshold in settings reference | — | Backend default; no project setting | Re-checked 2026-10-17: `amp --help` shows no compaction option |
| Cursor Agent 2026.10.01-e373342, Peer | No exposed threshold in help/bundled JS search | — | Backend default; no project setting | Re-checked 2026-10-17: `cursor-agent --help` shows no compaction option |
| Devin 3000.11.3, Peer | `agent.compaction_threshold_tokens=100000` in `~/.config/devin/config.json` | User-wide, **not workspace-scoped** | 100,000 | Applied user-wide (Human opt-in); existing file left untouched |
| Kiro 2.30 (kiro-cli acp v2), Supervisor/Lead/Peer | No exposed compaction threshold in `setup/kiro-*.json` agent schema | — | Backend default; no project setting | Re-checked 2026-10-17: no compaction key in agent JSON or `kiro-cli --help` |
| Factory Droid 0.241.1, Lead/Peer | No exposed threshold in `droid exec --help` / ACP surface | — | Backend default; no project setting | Re-checked 2026-10-17: `droid --help` shows no compaction option |
| Antigravity (agy_acp_server.par), Lead/Peer | No exposed threshold in probed session/new result | — | Backend default; no project setting | No compaction option in the probed ACP session/new result |

## Model windows

Source: local `~/.pi/agent/models-store.json`, exact IDs under `openrouter.models` or
`github-copilot.models`. The generated Pi catalog has no exact Haiku 5.5 entry either.
No sourced Pi window is ≤100k; a future such pin must be skipped rather than get a negative reserve.

| Pi pin | Context window | reserveTokens |
|---|---:|---:|
| `openrouter/deepseek/deepseek-v4.1-flash` | 1,048,576 | 948,576 |
| `openai-codex/gpt-6-luna` | 272,000 | 172,000 |
| `openrouter/moonshotai/kimi-k3` | 1,048,576 | 948,576 |
| `openrouter/z-ai/glm-5.3-flash` | 1,048,575 | 948,575 |
| `openrouter/z-ai/glm-5.3` | 1,048,576 | 948,576 |
| `openrouter/anthropic/claude-haiku-5.5` | Window unknown | Skipped (default compaction) |
