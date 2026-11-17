# SETUP — Two separate Amp seats through ACP

Use the backup, merge, MCP injection, contract/protocol, reload and live verification steps
in [SETUP.md](../../SETUP.md). You need the `amp-acp` executable and a signed-in Amp account.
Check discovery with `paseo provider models amp-acp --json` and `paseo provider diagnostic amp-acp --json`.
The adapter can fail to support `--version`. The ACP initialize/new-session diagnostic and an actual
launch are separate checks. A failed version command is not evidence that the launch failed.

Merge the two providers into `.agents.providers`. Do not replace the existing `amp-acp` provider:

| Field | `amp-lead` | `amp-peer` |
|---|---|---|
| `extends` | `acp` | `acp` |
| `command` | `["<KIT>/setup/role-agent", "lead", "amp"]` | `["<KIT>/setup/role-agent", "peer", "amp"]` |
| `enabled` | `true` | `true` |
| `env` | `{}` | `{}` |
| `paseoTools.enabled` | `true` | `true`, Peer deny-list (every catalog tool blocked; [SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)) |
| `models[0].id` | `medium` | `low` |
| `models[0].label` | `Medium` | `Low` |
| `models[0].isDefault` | `true` | `true` |

`amp-supervisor` uses `role-agent supervisor amp`, model `medium`/`high`, tools enabled; it has no thinking options.

Amp Lead uses the deny-list in [SETUP.md §3](../../SETUP.md); it does not apply to Peer.

Here `medium`/`low` are model IDs that Amp ACP exposes through Paseo. They are not separate
thinking options. Do not add fake `thinkingOptions`.

Profile pins:

| Seat | Model | Profile pins | Thinking options |
|---|---|---|---|
| `amp-lead` | `medium` | `amp-lead--medium` | None |
| `amp-peer` | `low` | `amp-peer--low` | None |
| `amp-supervisor` | `medium`, `high` | `amp-supervisor--medium`, `amp-supervisor--high` | None |

Select the permission mode from discovery (amp-acp v0.10.0 and v0.12.0, the ACP registry pin,
have only `local` and `orb`, and no bypass mode);
`amp-lead--medium` and `amp-peer--low` use `local`; `--check` requires `modeId: local` for every `amp-peer` profile. Replace `<KIT>` with the absolute
path, keep `role-agent` executable, then run `paseo reload` and create a new session.

The ACP proxy adds the role instructions to the first prompt of each new session, not to the system prompt.
A session restored with `session/load` or `session/resume` already has the role in its history, so the proxy
does not add it again. Check the Lead/Peer heading in the session content that the agent actually receives,
the actual CWD and the tool inventory: Lead must be able to call one read-only Paseo tool; Peer must not see
Paseo tools. Do not ask the agent to read the prompt file and treat that as proof of injection.
Lead coordinates with `amp-peer`, not with the original Amp provider.

Live resume: after a daemon restart, the new proxy sends
`session/load` with the same session ID, then the next prompt. A wrapper recorded the ACP requests that `amp-acp` received:
the proxy sent 1 role copy in total for two prompts (1, then 0). The agent still remembered the token from the first turn. `session/resume` and a real idle release after 1 hour are not checked yet.

Live E2E: `amp-peer` low launched through Paseo, the CWD was the
project, and no Paseo tool was visible. Amp wraps the prompt under its own `# Instructions` heading; the role heading
`# Peer — independent co-worker` still arrives intact. The native catalog has `Task`/`create_thread`
(Amp subagents); this is not Paseo MCP.

`setup-seats.sh --check` confirms the supervisor launcher, tools and model pin. The profile inventory includes Amp Lead medium, Amp Peer low and Supervisor medium/high. Check the two Amp providers and the live launch separately;
do not change the global Amp config, credentials or state to create role separation.
