# SETUP — Devin Peer and Supervisor through ACP

Use the common steps in [SETUP.md](../../SETUP.md), including the section
[ACP proxy seats](../../SETUP.md#acp-proxy-seats). Check the `devin` executable, auth and discovery first.

Devin has a Peer seat and a Supervisor seat. Do not configure a Devin Lead: `setup/devin-acp` rejects the `lead` role.

| Field | `devin-peer` | `devin-supervisor` |
|---|---|---|
| `command` | `["<KIT>/setup/role-agent","peer","devin"]` | `["<KIT>/setup/role-agent","supervisor","devin"]` |
| `paseoTools` | Peer deny-list (every catalog tool blocked; [SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)); only the plugin tool `epistex_submit_handoff` | Supervisor tool set ([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)) |
| `models` | only `swe-2-high` | only `swe-2-high` |
| `thinkingOptions` | `medium` (default), `high` | `medium` (default), `high` |
| Profile pin | `devin-peer--swe-2-high--medium`, `--high` | `devin-supervisor--swe-2-high--medium`, `--high` |
| `modeId` | `bypass` | `bypass` |

Do not configure the Fusion model. `swe-2-high` is the only model ID that Devin ACP accepts for SWE-2; it is not
an effort level. Effort is the ACP option `thought_level` (`medium`, `high`, `max`), and Paseo sets it from
`thinkingOptionId`. Live check: the medium profile reports "SWE-2 Medium", the high profile reports "SWE-2 High".

**Fast mode off.** Devin ACP has the option `speed` (`standard`, `fast`). `setup/devin-acp` sets `speed=standard`
for each new/load/resume session before the client knows that session, rejects requests to set another value, and rejects
a prompt when the backend has not confirmed `standard` (also when the backend changes to `fast` by itself during the session).

**Mode.** Devin ACP has `accept-edits`, `smart`, `ask`, `plan`, `bypass`. Paseo does not carry the Lead mode
over to another provider, so every profile has `modeId: bypass`; `--check` requires it. The other modes can stop an
unattended seat at a permission request.

`role-agent <role> devin` switches to `setup/devin-acp <role>` with `os.execv`; the launcher runs `devin acp`.

Live status (2026-11-14, Devin 3000.12.57, Paseo 0.15.4): `devin-peer` medium receives `# Common contract`
plus `# Peer — independent co-worker`, the correct CWD, and no Paseo tool. `devin-supervisor` high receives
`# Supervisor — Paseo-only observer`, sees exactly the Supervisor set of Paseo tools ([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)) and calls `list_workspaces` without a permission prompt.
ACP probe through the launcher (no prompt sent): `speed` is `standard`, and a `speed=fast` request is rejected.
Devin's own MCP servers (for example `figma`, `semble`) are still present; they are not Paseo MCP.
