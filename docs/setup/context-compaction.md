# Context compaction

Aim: compact near 200k tokens without changing role prompts or canonical Codex configuration.
Project settings apply when the seat's CWD is this checkout; seat env applies to every launch
of that role provider, so use these providers only for Epistex. Reload providers and launch new
sessions after installation. Static checks do not prove a live compaction; launch probes remain
with the Lead.

| Agent (verified version) | Mechanism | Scope | Effective threshold | Status |
|---|---|---|---|---|
| Codex 0.161.0, all roles | `model_auto_compact_token_limit=200000` in generated room TOML | Project/role runtime only | 200,000 | Configured in sync; CLI update blocked by the no-`~/.codex`-writes constraint |
| Claude 2.1.294, all enabled Claude seats (Supervisor, Lead, Peer) | `CLAUDE_CODE_AUTO_COMPACT_WINDOW=200000` | Epistex role-provider env | 200k window; backend buffer may trigger earlier; a model whose own window is 200k compacts at the backend default | Configured in example and applied live on all three Claude seats (2026-11-14); the launch probe of the env value in the Claude process was made with the earlier value `100000` on 2.1.294 |
| Pi 1.1.0, Peer | `.pi/settings.json`, per-model `reserveTokens` | Checkout | 200,000 for the six sourced pins below | Configured; Haiku window unknown — skipped (default compaction) |
| OMP 18.20.0, Supervisor/Lead/Peer | `.omp/config.yml`, `compaction.enabled=true`, `thresholdTokens=200000` | Checkout | 200,000 (clamped below model window) | Configured; ensure the `omp` on Paseo's PATH is 18.8.4 or newer (`omp --version`) |
| Copilot 1.0.108, Peer | No verified threshold variable in installed binary/help | — | Backend default; no project setting | `copilot --help` shows only `--context <tier>` (default/long_context), which is a window tier, not a threshold |
| Amp 0.0.1794312042, Supervisor/Lead/Peer | No exposed threshold in settings reference | — | Backend default; no project setting | `amp --help` shows no compaction option |
| Cursor Agent 2026.11.13-eacade1, Supervisor/Lead/Peer | No verified threshold in CLI configuration docs, help, ACP config options or bundled JS search | — | Backend default; no threshold configurable through a verified setting | `/summarize` (`/compress`) is manual, not an automatic threshold; no guessed setting added |
| Devin 3000.12.57, Supervisor/Peer | `agent.compaction_threshold_tokens=200000` in `~/.config/devin/config.json` | User-wide, **not workspace-scoped** | 200,000 | Applied user-wide (Human request, 2026-11-14); only this key was changed |
| Kiro 3.1.0 (kiro-cli acp v3), Supervisor/Lead/Peer | No exposed compaction threshold in `setup/kiro-*.json` agent schema | — | Backend default; no project setting | No compaction key in agent JSON, `kiro-cli --help` or `kiro-cli acp --help` |
| Factory Droid 1.7.0, Supervisor/Lead/Peer | `compactionTokenLimit=200000` in the `.factory/settings.json` of each seat home (`FACTORY_HOME_OVERRIDE`; `~/.factory/settings.json` for a seat on the stored login) ([settings docs](https://docs.factory.com/droid-cli/settings)) | Per seat home, **not workspace-scoped** | 200,000 | Set in the five seat homes (2026-11-14); no org-managed override found; live compaction not yet probed. No CLI flag; `droid --help` has no compaction option |
| Antigravity (`agy acp` 1.5.9), Lead/Peer | No exposed threshold in probed session/new result | — | Backend default; no project setting | No compaction option in the probed ACP session/new result |

## Model windows

Source: local `~/.pi/agent/models-store.json`, exact IDs under the provider model catalogs,
including `huggingface.models` and `openrouter.models`. The generated Pi catalog has no exact Haiku 5.5 entry either.
No sourced Pi window is ≤200k; a future such pin must be skipped rather than get a negative reserve.

| Pi pin | Context window | reserveTokens |
|---|---:|---:|
| `huggingface/deepseek-ai/DeepSeek-V4.1-Flash-1017` | 1,048,576 | 848,576 |
| `openrouter/deepseek/deepseek-v4.1-flash-1017` | 1,048,576 | 848,576 |
| `openai-codex/gpt-6-luna` | 272,000 | 72,000 |
| `openrouter/moonshotai/kimi-k3` | 1,048,576 | 848,576 |
| `openrouter/z-ai/glm-5.3-flash` | 1,048,575 | 848,575 |
| `openrouter/z-ai/glm-5.3` | 1,048,576 | 848,576 |
| `openrouter/anthropic/claude-haiku-5.5` | Window unknown | Skipped (default compaction) |
