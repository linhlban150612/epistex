# SETUP — Cursor Supervisor, Lead and Peer through ACP

Use the common steps in [SETUP.md](../../SETUP.md), including the section
[ACP proxy seats](../../SETUP.md#acp-proxy-seats). First check the `cursor-agent` executable, auth and discovery.

| Field | `cursor-supervisor` | `cursor-lead` | `cursor-peer` |
|---|---|---|---|
| `command` | `["<KIT>/setup/role-agent","supervisor","cursor"]` | `[…,"lead","cursor"]` | `[…,"peer","cursor"]` |
| `paseoTools` | Supervisor tool set ([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)) | Lead tool set ([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)) | No Paseo tools; only the plugin tool `epistex_submit_handoff` |
| `models` (first is default) | `grok-4.7-medium-500k`; `grok-4.7-high-500k` | `gemini-4-carbon-medium`; `gemini-4-carbon-high` | `composer-2.5`; `grok-4.7-low`; `grok-4.7-medium` |
| `thinkingOptions` | None; the launcher converts the model ID to ACP parameters | same as left | same as left |
| Profile pin | `cursor-supervisor--grok-4-7-medium-500k`, `--grok-4-7-high-500k` | `cursor-lead--gemini-4-carbon-medium`, `--high` | `cursor-peer--composer-2-5`, `--grok-4-7-low`, `--grok-4-7-medium` |
| `modeId` | `agent` | `agent` | `agent` (`plan`/`ask` do not write files) |

For each enabled seat, `--check` checks the launcher, the tools, the exact model list, the default and that all profiles exist with `modeId: agent`.
`role-agent <role> cursor` switches to `setup/cursor-acp <role>` with `os.execv`; the launcher runs
`cursor-agent acp`. The IDs above are seat IDs. They are not the IDs sent directly to Cursor ACP.

| Seat model ID | `model` | `reasoning_effort` | `context` | `fast` |
|---|---|---|---|---|
| `grok-4.7-medium-500k`, `grok-4.7-high-500k` | `grok-4.7` | `medium`, `high` | `500k` | `false` |
| `gemini-4-carbon-medium`, `gemini-4-carbon-high` | `gemini-4-carbon` | `medium`, `high` | none | none |
| `composer-2.5` | `composer-2.5` | none | none | `false` |
| `grok-4.7-low`, `grok-4.7-medium` | `grok-4.7` | `low`, `medium` | `256k` | `false` |

Each role can select only its own models; the launcher rejects models of other roles.

## Run Everything and Paseo tools

Cursor ACP has only the modes `agent`, `plan` and `ask`; it has no bypass mode. Without extra configuration, a seat
stops at a permission request on each shell command outside the Human allowlist and on each Paseo tool call
(checked live). Every Cursor seat runs in Run Everything: the launcher sets `"approvalMode": "unrestricted"`, the
setting that `--force`/`--yolo` turn on in the interactive CLI and that `cursor-agent acp` reads only from
`cli-config.json`. The launcher also adds the token `Mcp(paseo:<tool>)` to `permissions.allow` for exactly the Paseo
tools that the role keeps (the Lead set plus `epistex_assign`, the Supervisor set, the Peer only
`epistex_submit_handoff`; see [SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor); taken from
`setup/kiro-<role>.json`), so Paseo calls also run when a team admin blocks MCP auto-run. It does both only in the
seat's private copy of `cli-config.json`. The user's `cli-config.json` does not change. A team admin who disables Run
Everything overrides it.

Live (2026-11-17, CLI `2026.11.13-eacade1`): with the setting, `cursor-peer` ran a write command and `cursor-lead` a
read command outside the allowlist with no permission request; without it, the same prompts asked permission.

## Select model and reasoning level

On CLI `2026.10.18-ea085cb`, the CLI list contains `grok-4.7-low` and `grok-4.7-medium`,
but ACP rejects these two IDs by default. The ACP catalog publishes only variants taken from the saved
parameters. Because of this, a `high, fast=true` configuration can stay in effect when the client does not handle a model selection error.
Adding `--model` before `acp` did not fix the tested case.

The launcher declares `clientCapabilities._meta.parameterizedModelPicker=true`. After `session/new`
or `session/load`, the launcher uses `session/set_config_option` to set the parameters of the role's default model
from the table above (for example Peer: `model=composer-2.5`, `fast=false`). When Paseo selects a different profile,
the launcher sets the parameters of that model with the same protocol.
The launcher checks all values in the Cursor response before it accepts a prompt. If Cursor sends
`current_model_update` or `config_option_update` that conflicts with the confirmed selection, the launcher
cancels that confirmation and blocks the next prompt until the model is selected again and all values are confirmed.
The launcher does not track a session restored with `session/resume`, so it rejects prompts for that session; use `session/load` or create a new session.
If model selection fails or Cursor returns a different value, the launcher blocks the prompt. It does not fall back to Auto,
another model, another effort or Fast. Do not add `thinkingOptionId` to profiles.

Cursor writes ACP parameters to `cli-config.json`. The launcher uses a private copy through
`CURSOR_CONFIG_DIR` in a temporary directory with private permissions. The other files are linked to the original Cursor
directory to keep auth, MCP, rules and session history. `acp-config.json` is also kept separate.
Do not change the global model configuration. The temporary directory is deleted when the launcher exits; the original session history is kept.
Do not add `--force`, `--yolo` or `--approve-mcps` to the launch: `acp` has no such options, and Run Everything comes
from the private `cli-config.json`.

## Check after an update

After `paseo reload`, create a new session for each profile. Check the model, reasoning level, Fast off,
Peer role, CWD and the actual tools. The `paseoTools` deny-list does not disable Cursor's own MCP. Check that a shell command outside the Human allowlist runs without a permission request (Run Everything).
If Cursor reports a plan or quota limit, report BLOCKED; do not change the model or upgrade the plan.

## Automatic context compaction

The CLI has no token threshold option that is verified in the configuration docs, help or ACP config options
(checked again on `2026.11.13-eacade1`: ACP has only `mode`, `model`, `reasoning_effort`, `context`, `fast`).
Keep the backend default behavior; do not add guessed keys. The 200.000-token threshold of the other seats
does not apply to Cursor. `/summarize` (alias `/compress`) is a manual command.

Sources: [ACP](https://cursor.com/docs/cli/acp),
[CLI configuration](https://cursor.com/docs/cli/reference/configuration),
[CLI capabilities](https://cursor.com/docs/cli/using),
[Grok 4.7](https://cursor.com/docs/models/grok-4-7).
The parameter selection capability and the response values were checked directly on the version above.

Live (2026-11-14, CLI `2026.11.13-eacade1`, Paseo 0.15.4): `cursor-peer` `composer-2.5` received `# Common contract`
plus the Peer heading, correct CWD, no Paseo tools. The native catalog has `Task` (Cursor's subagent) and the Human's own
MCP (for example `semble`); these are not Paseo MCP. `cursor-supervisor` `grok-4.7-high-500k` saw exactly the Supervisor Paseo tool set ([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor));
`cursor-lead` saw the Lead tool set plus `epistex_assign`. Both called Paseo tools without a permission request.
The parameter catalog of the three models came from an ACP probe that sent no prompt.
