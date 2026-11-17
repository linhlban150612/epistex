# SETUP — GitHub Copilot Peer through ACP

Use the common steps in [SETUP.md](../../SETUP.md), including the section
[ACP proxy seats](../../SETUP.md#acp-proxy-seats). Check the `copilot` executable, auth and discovery first.

Copilot has only a Peer seat: `setup/copilot-acp` rejects every role other than `peer`.

| Field | `copilot-peer` |
|---|---|
| `command` | `["<KIT>/setup/role-agent","peer","copilot"]` |
| `paseoTools.enabled` | `true`, Peer deny-list (every catalog tool blocked; [SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)); only the plugin tool `epistex_submit_handoff` |
| `models` | `gemini-3.8-flash`, `kimi-k3`, `claude-haiku-5.5`, `grok-4.7`, `claude-sonnet-5.5` |
| `thinkingOptions` | `low`, `medium` for each model |

Profile pins: each model at `low` and `medium` (10 profiles `copilot-peer--<model-slug>--<thinking>`).

`role-agent peer copilot` switches to `setup/copilot-acp peer` with `os.execv`; the launcher runs
`copilot --acp`. ACP currently returns the mode `https://agentclientprotocol.com/protocol/session-modes#agent`
for the smoke-test session; do not infer the mode ID `default` from the label/default summary.
