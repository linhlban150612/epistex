# Factory Droid seats

This guide covers `droid-peer`, `droid-lead` and `droid-supervisor`, Paseo seats backed by Factory Droid through the ACP proxy in
`setup/role-agent`. Paseo remains the only lifecycle/topology owner. The seat is a role-wrapped
provider: do not use the plain `factory-droid` provider or attach Peer profiles to it, because that
provider does not inject the common contract and the selected role prompt
(`agents/contract/COMMON.md` + the role file).

## Prerequisites

1. Install Factory Droid and ensure the `droid` binary is on the PATH inherited by Paseo.
   `role-agent peer droid` runs `droid exec --output-format acp-daemon --settings <guard file>` with
   `DROID_DISABLE_AUTO_UPDATE=true` and `FACTORY_DROID_AUTO_UPDATE_ENABLED=false`: the launch
   arguments and environment of the [ACP registry](https://github.com/agentclientprotocol/registry)
   entry `factory-droid` (registry pin: 1.9.0). The launcher sets the two variables; do not add them
   to the provider `env`. Verified versions: 1.0.0, 1.1.0 and 1.4.1 with `acp`; 1.7.1 with `acp` and
   `acp-daemon`; 1.9.0 with `acp-daemon`.
2. Authenticate Droid before launching a seat: use Factory's login flow (shared by all seats), or
   give each seat its own key (see [Per-seat API keys](#per-seat-api-keys)). Credentials stay in
   Droid's user state or in the Paseo config, never in this repository.
3. The seat does not offer Droid's `auto` ("Auto Model", reasoning `none` only). The seat's model
   list contains exactly the models in the table below.

## Configure Paseo

Merge the `droid-peer` entry and its `droid-peer--*` profiles from
`examples/paseo-providers.json`; replace `<KIT>` with the absolute repository path.

| Field | Value |
|---|---|
| Provider | `droid-peer`, extends `acp` |
| Command | `["<KIT>/setup/role-agent","peer","droid"]` |
| Paseo tools | Disabled |
| Default model | `claude-haiku-5-5`, default effort `low` |
| Models/profiles | Nine models, 17 supported profiles listed below; each defaults to `low` |

Each model exposes only its requested supported low/medium or low/high choices, not every upstream effort. The checker requires every `droid-peer` profile to
carry a valid `thinkingOptionId` and `modeId: "auto-high"`. The orchestrator must copy provider, model,
`thinkingOptionId` and `modeId` into `create_agent`. Without `auto-high` a Peer starts in Droid's
`normal` mode and stops on its first `edit` permission request; with it the edit runs without a
request (both verified live).

`setup-seats.sh --check` validates the seat and profile only when `droid-peer` is enabled, so
configs without Droid still pass.

## Seat guard hook

Droid has native subagents, Missions, loops and automations. Paseo owns agent lifecycle and
topology, and roles create no schedules, so every Droid seat denies these tools: `Task`,
`TaskOutput`, `TaskStop`, `ProposeMission`, `StartMissionRun`, `Loop`, `CreateAutomation`,
`EditAutomation`, `DeleteAutomation`, `RunAutomation`. Other tools, Paseo MCP and Script stay
available.

A Lead or Supervisor seat is also denied an `Execute` command that runs `git commit`, `git push`,
`git merge`, `git worktree remove` or a deploy (`<tool> deploy`, `npm run deploy`): the Peer is the
only writer, and Human approval of such an action is routed to a Peer. Read commands such as
`git merge-base`, `git worktree list` and `rg deploy` stay allowed.

A Peer seat is denied three destructive `Execute` forms, the same rule set as the Claude Peer guard
(`setup/seat_guard.py`):

- `rm` with a recursive flag and a force flag on a path outside the workspace. A path below `/tmp`
  or `/var/tmp` is allowed. A path the guard cannot read as text (`$VAR`, `$(…)`) is denied.
- `git push` with `--force`, `-f`, `--force-with-lease`, `--mirror` or a `+refspec`.
- `git reset --hard`.

The workspace is `$FACTORY_PROJECT_DIR` when Droid sets it, else the Git top level of the hook's
`cwd`, else that `cwd`. The denial tells the Peer to use a narrower command or report `BLOCKED`.

- `role-agent <role> droid` writes a private settings file with a `PreToolUse` hook that runs
  `setup/droid-guard <role>`, and starts `droid exec --output-format acp-daemon --settings <file>`. It removes
  the file when the seat exits (SIGTERM included; a SIGKILL leaves the small file in `$TMPDIR`).
  No manual setup; the seat's `settings.json` is not changed.
- The hook runs for direct calls and for each tool call inside a Script, and exit code 2 rejects
  the call. Unreadable hook input is also rejected.
- `role-agent` rejects a `--settings` launch argument, because a second settings file could drop
  the hook.
- `setup-seats.sh --check` fails when any Droid seat is enabled and `setup/droid-guard` is not
  executable, does not allow `Glob`, does not deny `Task` with exit code 2, does not deny
  `git push` for a Lead, or does not deny `git reset --hard` for a Peer. It also fails when a seat
  home's `.factory/settings.json` sets `hooksDisabled: true`, because that setting stops the guard.

Why a hook: Droid 1.0.0 ACP accepts `--remove-tools`/`--only-tools` silently and ignores them, and
ACP has no tool config option. Paseo MCP calls inside Script stay allowed: Opus 5.5 runs in Droid's
`script_only` mode, where Paseo tools are callable only inside a Script.

Live probe (Droid 1.0.0, through Paseo): `droid-peer`, `droid-lead` and `droid-supervisor` each got
`Epistex seat policy denies Task` for a `Task` call. Lead and Supervisor completed
`list_workspaces`, and Peer completed `Glob`. A direct ACP probe also rejected `Loop` inside a
Script.

Live probe of the Peer command check (Droid 1.7.1, through Paseo 0.15.4, `gemini-3.8-flash`, started
in a subdirectory of a test repository): `droid-peer` ran `git status`, and got
`Epistex seat policy denies git reset --hard in a Peer seat` and
`Epistex seat policy denies rm -rf outside the workspace` for the two destructive commands.

## Additional model capabilities and profiles

The capability source is a direct ACP inventory (last checked on Droid 1.1.0): start
`droid exec --output-format acp`, initialize a session without a prompt, select each
model using `session/set_config_option` with `configId=model`, then inspect the returned
`reasoning_effort` select. This verifies advertised per-model choices, not successful model
execution, authentication for inference, or Paseo integration. No model prompt was executed.

| Model ID | ACP-advertised reasoning efforts | Exposed choices / profile suffixes |
|---|---|---|
| `gemini-4-argon` | low, medium, high | low, medium |
| `gemini-3.8-flash` | low, medium, high | low, medium |
| `claude-opus-5-5` | low, medium, high, xhigh, max | low, medium |
| `claude-sonnet-5-5` | off, low, medium, high, xhigh, max | low, medium |
| `claude-haiku-5-5` | off, low, medium, high, xhigh, max | low, medium |
| `gpt-6.1-sol` | low, medium, high, xhigh, max | low, medium |
| `glm-5.3` | low, high, max | low, high |
| `kimi-k3` | off, low, high, max | low, high |
| `deepseek-v4.1-flash-1017` | off, low, high, max | low (requested: low only) |

Profile IDs follow `droid-peer--<model-id-with-dots-replaced-by-hyphens>--<effort>`, for example
`droid-peer--gpt-6-1-sol--medium`; the profile's `model` stays `gpt-6.1-sol`. There are 17 Droid
profiles total. The checker requires all supported profiles and rejects missing or extra models,
missing choices, mismatched provider/model/effort, and fabricated medium options or profiles for the
low/high models.

For `glm-5.3` and `kimi-k3` only `low` and `high` are offered because medium is not advertised for
those models.

Paseo's `factory-droid` metadata advertises generic thinking options across models; it is not the
per-model capability source. Likewise, `droid exec --list-tools` exiting 0 with medium for the
low/high models does not prove runtime medium support.

## Known limitations

- Role instructions are added to each new session's first prompt by the ACP proxy, not to the system
  prompt. A session restored with `session/load` or `session/resume` does not get them again.
- Droid Lead/Supervisor use the injected Paseo MCP; Droid Peer has Paseo tools disabled.
- The [seat guard hook](#seat-guard-hook) denies tools by name, and Lead/Supervisor write commands
  and Peer destructive commands by a pattern on the command text. It is not an OS sandbox: a seat
  can still start processes through `Execute`, and a command the pattern does not know (a script
  that pushes, `./deploy.sh`, `find -delete`, a file tool) passes. Droid seats and the Claude Peer
  seat have a guard hook; other backends rely on the role prompt.
- Static checks do not prove authentication, the `acp-daemon` output mode, effort mapping or runtime
  integration. The operator merges/reloads the config and performs an actual Paseo launch.
  Last verified launches (Droid 1.9.0, `acp-daemon`, `low`, `auto-high`): `droid-peer`
  (`gemini-3.8-flash`), `droid-lead` and `droid-supervisor` (`claude-sonnet-5-5`). Each seat got the
  role instructions, the session cwd and the two auto-update variables; the Peer guard denied
  `git reset --hard` and the Peer saw no Paseo tools; Lead and Supervisor completed `list_workspaces`.
  Session restore (Droid 1.9.0, `droid-peer`): after `paseo agent reload`, Paseo sent `session/load`
  to a new proxy and the seat still knew the earlier turn. A direct ACP run through
  `role-agent peer droid` restored one session with `session/resume` and with `session/load`, each
  in a new process; the proxy did not add the role instructions again, and the `session/load`
  replay held them one time.


## droid-lead

Provider `droid-lead`, command `["<KIT>/setup/role-agent","lead","droid"]`, Lead Paseo tool policy
per SETUP.md (51-entry deny-list). Models `claude-opus-5-5`, `claude-sonnet-5-5`, `gpt-6.1-sol`,
`gemini-4-argon` with low/medium effort. Profiles carry `modeId: "auto-high"` (all operations are
auto-approved, so Lead never waits for permission). Droid's advertised modes: `normal`, `spec`, `auto-low`,
`auto-medium`, `auto-high`.

## droid-supervisor

Provider `droid-supervisor`, command `["<KIT>/setup/role-agent","supervisor","droid"]`, Supervisor
Paseo tool policy per SETUP.md (46-entry deny-list). Same four models and low/medium efforts as
`droid-lead`; default `claude-sonnet-5-5`, `low`. Profiles `droid-supervisor--<model>--<effort>`
carry `modeId: "auto-high"`: in `normal`, `auto-low` and `auto-medium` the seat stops on a
permission request for every Paseo MCP call (verified live with `list_workspaces`).

## Per-seat API keys

To bill or track each role on a different Factory key, give each seat its key **and** its own Droid
home in the live Paseo config (`~/.paseo/config.json`), then run `paseo reload`.

Droid cannot combine a key with the stored login in `~/.factory`: `session/new` succeeds, then
`session/set_config_option` returns `Unknown session identifier` and the prompt fails with
`Session not found` (`assertSessionAccessibleForOrganization`). Paseo always sets model and effort,
so every launch fails. `FACTORY_HOME_OVERRIDE` moves Droid's state to `$FACTORY_HOME_OVERRIDE/.factory`,
where no stored login exists.

1. Back up the config and create one state dir per seat (outside the kit; not a symlink):

   ```bash
   cp -p ~/.paseo/config.json ~/.paseo/config.json.bak-droid-home-$(date +%Y%m%d%H%M%S)
   for r in peer lead supervisor; do
     mkdir -p ~/.local/state/epistex/droid/$r/.factory
     install -m 600 ~/.factory/settings.json ~/.local/state/epistex/droid/$r/.factory/settings.json
   done
   chmod -R go-rwx ~/.local/state/epistex/droid
   ```

   The copy keeps `compactionTokenLimit`, `sessionDefaultSettings` and hooks. Copy, do not symlink:
   a symlink lets one seat write the global file, and an atomic rewrite would silently replace the
   link. Droid reads only this copy (without it the limit falls back to 250000), so after each change
   to `~/.factory/settings.json`, run the `install` line again for all three seats. Do not copy `auth*`
   files. `mcp.json`, custom droids and plugins are not copied; Lead/Supervisor get Paseo MCP
   through ACP.
2. Set the env of each seat (absolute paths; `~` is not expanded):

   ```json
   "droid-peer": { "env": { "FACTORY_API_KEY": "fk-...",
     "FACTORY_HOME_OVERRIDE": "/home/<user>/.local/state/epistex/droid/peer" } }
   ```

   Repeat with `lead` and `supervisor`.
3. Run `paseo reload`, `setup-seats.sh --check` and one Paseo launch per seat.

Rollback: restore the backup, run `paseo reload`, then remove `~/.local/state/epistex/droid`
when you no longer need its session history. `~/.factory` is not changed.

Notes:

- Verified live: all three seats completed a Paseo prompt; Lead and Supervisor called
  `list_workspaces`. Sessions went to each seat's dir; no `auth*` file was created. The agent's
  file tool resolved `~/` to the real home and shell `$HOME` stayed unchanged.
- `FACTORY_HOME_OVERRIDE` is not in Factory's docs (found in the `droid` binary). Re-check it after
  each Droid update.
- An invalid key fails with `Authentication failed`, so the key is used for auth.
- `setup-seats.sh --check` accepts `env` that is `{}` or exactly `FACTORY_API_KEY` (`fk-` prefix)
  plus an absolute `FACTORY_HOME_OVERRIDE`. Each home must be unique, exist, sit outside the kit
  and not be a symlink (nor its `.factory`). Its `.factory/settings.json` must be a regular file with
  `compactionTokenLimit` 100000.
- Never put a key in `examples/paseo-providers.json` or another tracked file.
- Separate keys separate usage and billing, not access: all roles run as the same Unix user, so
  every agent can read the Paseo config and its keys.
