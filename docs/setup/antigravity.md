# Antigravity Peer and Lead seats

This guide adds `agy-peer`, a Paseo Peer, and `agy-lead` (see [Lead seat](#lead-seat)). Both run `agy acp`, the ACP server built into the Antigravity CLI `agy`. Paseo remains the only lifecycle/topology owner. Do not enable `agy remote-control`.

## One Antigravity instance

The seats use the same binary and the same state as the Human's own `agy` sessions (`agy --conversation=…`): login, models and conversations live in `~/.gemini/antigravity-cli/`. Do not use the separate registry binary `agy_acp_server.par` ([ACP registry](https://github.com/agentclientprotocol/registry/blob/main/antigravity-acp/agent.json) entry `antigravity-acp`) for a seat: it keeps its own login in `~/.gemini/antigravity-acp/`, and that login can offer fewer models.

Observed on 2026-11-14: with the registry binary (the installed build and 1.5.0), `session/new` offered only `gemini-3.8-flash-*` and a request for `gemini-4-argon-low` failed with `not available for the current authentication method`. Paseo logged no error and the `agy-lead` session ran `gemini-3.8-flash-high`. `agy acp` 1.5.9 offered the full catalog of `agy models` and accepted the request.

## Prerequisites

1. Install the Antigravity CLI so that `agy` is on Paseo's PATH, and log in with `agy`. `agy models` must list every model the seats use.
2. `setup/role-agent <role> agy` switches to `setup/agy-acp <role>`, which runs `agy acp`. Never add `--dangerously-skip-permissions`. Paseo's built-in `antigravity` provider always passes it and skips `setup/role-agent`, so do not use it for any Epistex seat; `setup/agy-acp` rejects the flag.

## Configure Paseo

Merge the `agy-peer` entry and its model profiles from `examples/paseo-providers.json`; replace `<KIT>` with the absolute repository path. The provider extends `acp`, invokes `setup/role-agent peer agy`, and has Paseo tools disabled.

| Seat | Models (first is the default) | `modeId` |
|---|---|---|
| `agy-peer` | `gemini-3.8-flash-low`, `gemini-3.8-flash-medium`, `gemini-4-argon-low`, `gemini-4-argon-medium`, `gemini-4-hydrogen-low`, `gemini-4-hydrogen-medium` | `accept-edits` |
| `agy-lead` | `gemini-4-argon-low`, `gemini-4-argon-medium` | `default` |

A seat model ID carries the effort: `agy acp` maps `gemini-4-argon-low` to model `gemini-4-argon` with `thought_level` `low`, so profiles have no `thinkingOptionId`. `setup-seats.sh --check` enforces the model lists, the profiles and the modes.

`agy acp` advertises the modes `default`, `accept-edits` and `plan`; `plan` does not write. Each `daemon.agentProfiles` entry selects the mode with `modeId`, and the orchestrator must copy it into `create_agent`. Verified live: a Peer in `accept-edits` created a file and ran shell commands with no permission request; a Lead in `default` ran shell reads and Paseo tools with no permission request.

`role-agent` states the session cwd in each session's first prompt, together with the role instructions; after `session/load` or `session/resume` in a new proxy process it repeats only the cwd line, because the restored history already holds the role. The registry binary needed this line, because it ran shell commands in its own directory. `agy acp` ran `pwd` in the session cwd in every live check; the line is kept.

## Lead seat

`agy-lead` invokes `setup/role-agent lead agy`, so every new session's first prompt carries `agents/contract/COMMON.md` followed by `agents/LEAD.md`. It enables Paseo tools with the same `disabledTools` deny-list as every other `*-lead` seat; `setup-seats.sh --check` enforces the exact list. It also requires `daemon.mcp.injectIntoAgents`.

`agy acp` does not advertise `mcpCapabilities`, but it accepts the Paseo MCP server of `session/new`: a real launch showed the eight Lead tools and `epistex_assign`, and `list_workspaces` and `list_profiles` returned results. Do not work around missing tools with user-wide `agy mcp add`.

## State and known limitations

- Seat sessions are stored with the Human's own conversations in `~/.gemini/antigravity-cli/`. This is private runtime state and must remain outside the repository.
- A seat uses the Human's CLI login and its quota.
- Model confirmation: Paseo does not stop a session when the backend refuses the requested model. `setup/agy-acp` therefore records each model the client selects (`session/set_model`, or `session/set_config_option` with `configId=model`) and refuses `session/prompt` when the backend refused that selection, or when the `model` and `thought_level` it reports differ from the selected ID. After `session/set_model` the backend answers `{}` and reports the state in a `config_option_update`; a prompt waits up to 10 seconds for that report and is refused without it. A session with no selection runs the backend's current model and is not judged. The launcher does not know the seat's model list: Paseo's provider `models` limit what a profile can select.
- Select the effort through the model ID. A separate `thought_level` change after a selection makes the reported state differ from the selected ID, and the next prompt is refused until a model is selected again.
- Not verified with `agy acp`: `session/load` and `session/resume` through Paseo (verified earlier only with the registry binary), and cancelling a running prompt.
- Static checks do not establish that authentication or runtime integration works; perform an actual Paseo launch.

Live status of model confirmation (2026-11-14, raw ACP through the launcher): after a refused selection (`Unknown model ID`), the prompt was refused by the seat; after `gemini-4-argon-low` was selected, the prompt ran.

Live status (2026-11-14, `agy` 1.5.9, Paseo 0.15.4): `agy-lead` `gemini-4-argon-low` reported "Gemini 4 Argon (Low)", the Lead heading, the session cwd and nine Paseo tools. `agy-peer` `gemini-4-argon-low` and `gemini-4-hydrogen-low` reported their model, the Peer heading, the session cwd and no Paseo tool, and each wrote a file. Through `epistex_assign`, a `droid-lead` created an `agy-peer--gemini-4-hydrogen-medium` Peer: it reported "Gemini 4 Hydrogen (Medium)", wrote its file with no permission request, and the Lead got one `HANDBACK_VALID`. With the confirming launcher, `agy-lead` `gemini-4-argon-medium` and `agy-peer` `gemini-4-hydrogen-low` reported their model and completed their prompts through Paseo.
