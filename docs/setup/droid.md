# Factory Droid seats

This guide covers `droid-peer` and `droid-lead`, Paseo seats backed by Factory Droid through the ACP proxy in
`setup/role-agent`. Paseo remains the only lifecycle/topology owner. The seat is a role-wrapped
provider: do not use the plain `factory-droid` provider or attach Peer profiles to it, because that
provider does not inject `agents/PEER.md`.

## Prerequisites

1. Install Factory Droid and ensure the `droid` binary is on the PATH inherited by Paseo.
   `role-agent peer droid` runs `droid exec --output-format acp`.
2. Authenticate Droid with Factory's supported login flow before launching a seat. Credentials stay
   in Droid's user state, never in this repository.
3. Droid 0.241.1 reports `auto` ("Auto Model") with reasoning `none` only, and `gpt-6-luna`
   ("GPT-6 Luna") with `none`, `low`, `medium`, `high`, `xhigh`, `max`, default `medium`. The seat
   keeps Paseo's `off` id for Droid's `none`.   The seat's model list contains exactly the models in the table below.

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

The capability source is the Lead's direct ACP inventory of Droid 0.241.1: start
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

- Role instructions are added to each session's first prompt by the ACP proxy, not to the system
  prompt.
- Droid does not support Paseo MCP through this configuration; Peers have Paseo tools disabled anyway.
- Static checks do not prove authentication, the `acp` output mode, effort mapping or runtime
  integration. The operator merges/reloads the config and performs an actual Paseo launch.


## droid-lead

Provider `droid-lead`, command `["<KIT>/setup/role-agent","lead","droid"]`, Lead Paseo tool policy
per SETUP.md (50-entry deny-list). Models `claude-opus-5-5`, `claude-sonnet-5-5`, `gpt-6.1-sol`,
`gemini-4-argon` with low/medium effort. Profiles carry `modeId: "auto-high"` (all operations are
auto-approved, so Lead never waits for permission). Droid's advertised modes: `normal`, `spec`, `auto-low`,
`auto-medium`, `auto-high`.
