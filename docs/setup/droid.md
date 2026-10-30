# Factory Droid seats

This guide covers `droid-peer`, `droid-lead` and `droid-supervisor`, Paseo seats backed by Factory Droid through the ACP proxy in
`setup/role-agent`. Paseo remains the only lifecycle/topology owner. The seat is a role-wrapped
provider: do not use the plain `factory-droid` provider or attach Peer profiles to it, because that
provider does not inject the common contract and the selected role prompt
(`agents/contract/COMMON.md` + the role file).

## Prerequisites

1. Install Factory Droid and ensure the `droid` binary is on the PATH inherited by Paseo.
   `role-agent peer droid` runs `droid exec --output-format acp`. Verified version: 0.247.0
   (`droid update --version 0.247.0`). The ACP registry entry for 0.247.0 launches
   `--output-format acp-daemon`; the seat keeps `acp`, which 0.247.0 still supports.
2. Authenticate Droid before launching a seat: use Factory's login flow (shared by all seats), or
   give each seat its own key (see [Per-seat API keys](#per-seat-api-keys)). Credentials stay in
   Droid's user state or in the Paseo config, never in this repository.
3. Droid 0.247.0 reports `auto` ("Auto Model") with reasoning `none` only, and `gpt-6-luna`
   ("GPT-6 Luna") with `none`, `low`, `medium`, `high`, `xhigh`, `max`, upstream default `medium`
   (observed on 0.241.1; `~/.factory/settings.json` `reasoningEffort` overrides it). The seat
   keeps Paseo's `off` id for Droid's `none`. The seat's model list contains exactly the models in the table below.

## Configure Paseo

Merge the `droid-peer` entry and its `droid-peer--*` profiles from
`examples/paseo-providers.json`; replace `<KIT>` with the absolute repository path.

| Field | Value |
|---|---|
| Provider | `droid-peer`, extends `acp` |
| Command | `["<KIT>/setup/role-agent","peer","droid"]` |
| Paseo tools | Disabled |
| Default model | `gpt-6-luna`, default effort `low` (the seat default; upstream defaults to `medium`) |
| Luna profiles | `droid-peer--gpt-6-luna--low`; `droid-peer--gpt-6-luna--medium` |
| Additional models/profiles | Ten models, 20 supported profiles listed below; each defaults to `low` |

Luna retains its six thinking options. Each additional model exposes only its requested supported
low/medium or low/high choices, not every upstream effort. The checker requires every `droid-peer` profile to
carry a valid `thinkingOptionId`. The orchestrator must copy provider, model and `thinkingOptionId`
into `create_agent`.

`setup-seats.sh --check` validates the seat and profile only when `droid-peer` is enabled, so
configs without Droid still pass.

## Additional model capabilities and profiles

The capability source is a direct ACP inventory of Droid 0.241.1, re-checked unchanged on 0.247.0
(2026-10-22): start
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
| `glm-5.3-flash` | low, high, max | low, high |
| `glm-5.3` | low, high, max | low, high |
| `kimi-k3` | off, low, high, max | low, high |
| `deepseek-v4.1-flash` | off, low, high, max | low, high |

Profile IDs follow `droid-peer--<model-id-with-dots-replaced-by-hyphens>--<effort>`, for example
`droid-peer--gpt-6-1-sol--medium`; the profile's `model` stays `gpt-6.1-sol`. There are 22 Droid
profiles total: two existing Luna profiles plus 20 additions. The checker requires all supported
profiles and rejects missing models/choices, mismatched provider/model/effort, and fabricated medium
options or profiles for the four low/high models.

For `glm-5.3-flash`, `glm-5.3`, `kimi-k3` and `deepseek-v4.1-flash` only `low` and `high` are
offered because medium is not advertised for those models.

Paseo's `factory-droid` metadata advertises generic thinking options across models; it is not the
per-model capability source. Likewise, `droid exec --list-tools` exiting 0 with medium for the four
low/high models does not prove runtime medium support.

## Known limitations

- Role instructions are added to each new session's first prompt by the ACP proxy, not to the system
  prompt. A session restored with `session/load` or `session/resume` does not get them again.
- Droid Lead/Supervisor use the injected Paseo MCP; Droid Peer has Paseo tools disabled.
- Static checks do not prove authentication, the `acp` output mode, effort mapping or runtime
  integration. The operator merges/reloads the config and performs an actual Paseo launch.
  Last verified on 0.247.0 (2026-10-22): `droid-peer` (`gpt-6-luna`, `low`) and `droid-lead`
  (`claude-opus-5-5`, `low`, `auto-high`) completed a Paseo prompt.


## droid-lead

Provider `droid-lead`, command `["<KIT>/setup/role-agent","lead","droid"]`, Lead Paseo tool policy
per SETUP.md (50-entry deny-list). Models `claude-opus-5-5`, `claude-sonnet-5-5`, `gpt-6.1-sol`,
`gemini-4-argon` with low/medium effort. Profiles carry `modeId: "auto-high"` (all operations are
auto-approved, so Lead never waits for permission). Droid's advertised modes: `normal`, `spec`, `auto-low`,
`auto-medium`, `auto-high`.

## droid-supervisor

Provider `droid-supervisor`, command `["<KIT>/setup/role-agent","supervisor","droid"]`, Supervisor
Paseo tool policy per SETUP.md (46-entry deny-list). Same four models and low/medium efforts as
`droid-lead`; default `claude-sonnet-5-5`, `low`. Profiles `droid-supervisor--<model>--<effort>`
carry `modeId: "auto-high"`. Live probe on Droid 0.251.0 (2026-10-29): in `normal`, `auto-low` and
`auto-medium` the seat stopped on a permission request for the Paseo MCP call `list_workspaces`; in
`auto-high` it completed the call and showed the common contract as its first role-instruction line.

## Per-seat API keys

To bill or track each role on a different Factory key, give each seat its key **and** its own Droid
home in the live Paseo config (`~/.paseo/config.json`), then run `paseo reload`.

Droid 0.251.0 cannot combine a key with the stored login in `~/.factory`: `session/new` succeeds,
then `session/set_config_option` returns `Unknown session identifier` and the prompt fails with
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

- Live probe (2026-10-29, Droid 0.251.0): all three seats completed a Paseo prompt; Lead and
  Supervisor called `list_workspaces`. Sessions went to each seat's dir; no `auth*` file was created.
  The agent's file tool resolved `~/` to the real home and shell `$HOME` stayed unchanged.
- `FACTORY_HOME_OVERRIDE` is not in Factory's docs (found in the 0.251.0 binary). Re-check it after
  each Droid update.
- An invalid key fails with `Authentication failed`, so the key is used for auth.
- `setup-seats.sh --check` accepts `env` that is `{}` or exactly `FACTORY_API_KEY` (`fk-` prefix)
  plus an absolute `FACTORY_HOME_OVERRIDE`. Each home must be unique, exist, sit outside the kit
  and not be a symlink (nor its `.factory`). Its `.factory/settings.json` must be a regular file with
  `compactionTokenLimit` 100000.
- Never put a key in `examples/paseo-providers.json` or another tracked file.
- Separate keys separate usage and billing, not access: all roles run as the same Unix user, so
  every agent can read the Paseo config and its keys.
