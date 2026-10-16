# Antigravity Peer and Lead seats

This guide adds `agy-peer`, a Paseo Peer, and an example `agy-lead` seat (see [Lead seat](#lead-seat)), each backed by Google's official Antigravity ACP server (`antigravity-acp`, listed in the [ACP registry](https://github.com/agentclientprotocol/registry/blob/main/antigravity-acp/agent.json)). Paseo remains the only lifecycle/topology owner. Do not enable `agy remote-control`.

## Prerequisites and install

1. Download the pinned registry release for your platform (Linux x86_64, version 1.4.0):

   ```sh
   curl -fsSLO https://dl.google.com/agy-extensions/releases/linux/agy-acp-server-1.4.0-linux-x86_64.zip
   sha256sum agy-acp-server-1.4.0-linux-x86_64.zip
   # fbb2d54dd94fb897845308d3b6b46187c627f1c60078ded81adeeaf8b90c5d7a
   unzip agy-acp-server-1.4.0-linux-x86_64.zip
   install -m 755 agy_acp_server.par localharness_external ~/.local/bin/
   ```

   Other platforms use the archives listed in the registry `agent.json`. Ensure `~/.local/bin` is on Paseo's PATH. The archive and binaries are not tracked in this repository.
2. `setup/role-agent <role> agy` runs `agy_acp_server.par --uid=` (the registry's Linux arguments; `--uid=` keeps the server from switching user when run as root).
3. Authenticate the server yourself before launching a seat: set `auth.type` in `~/.gemini/antigravity-acp/settings.json` (`oauth-personal`, `gemini-api-key` with `GEMINI_API_KEY`, `oauth-business`, `agent-platform` or `gateway`) or complete ACP `authenticate`. Without it, `session/new` fails with `Authentication required`. This state is separate from the `agy` CLI's `~/.gemini/antigravity-cli/` and must never be copied into tracked files.

## Configure Paseo

Merge the `agy-peer` entry and its model profiles from `examples/paseo-providers.json`; replace `<KIT>` with the absolute repository path. The provider extends `acp`, invokes `setup/role-agent peer agy`, and has Paseo tools disabled.

**Pending verification:** the server's `session/new` advertises modes `default`, `auto_edit` (auto-approve file edit tools) and `yolo` (auto-approve everything — never used here), and the model IDs above. The seat's mode is selected via `modeId` on each `daemon.agentProfiles` entry (`auto_edit` for `agy-peer`, `default` for `agy-lead`), which Paseo applies when creating the agent; the orchestrator must copy `modeId` into `create_agent` alongside `provider` and `model`. `auto_edit` auto-approves file edits only — shell commands still prompt — and the seat has no plan mode: `plan` exists only as a `/plan` slash command. Whether the mode lands and how permissions behave in practice remain unverified; re-verify the mode/permission policy with an actual Paseo launch before relying on either seat.

ACP `session/new` carries the agent cwd; whether the server honours it is unverified. Never use `--dangerously-skip-permissions`. Paseo's built-in `antigravity` provider always passes it; do not use it for a Lead.

## Lead seat

`agy-lead` invokes `setup/role-agent lead agy`, so every session's first prompt carries `agents/LEAD.md`. It enables Paseo tools with the same 47-tool `disabledTools` deny-list as every other `*-lead` seat; `setup-seats.sh --check` enforces the exact list. It also requires `daemon.mcp.injectIntoAgents`.

Unlike the Peer, `agy-lead` runs in the server's `default` mode (set via each `agy-lead` profile's `modeId`), so every tool call prompts; there is no plan mode — `plan` is only a `/plan` slash command, not an ACP session mode.

The official server advertises `mcpCapabilities` `http` and `sse`; Paseo forwards its MCP tools to `agy-lead` over these. Do not work around missing tools with user-wide `agy mcp add`.

## State and known limitations

The server reads its settings from `~/.gemini/antigravity-acp/settings.json`. This is private runtime state and must remain outside the repository.

- The server advertises `loadSession`, `session/list` and `session/resume`. Cancelling a running prompt through Paseo returns the agent to idle; session resume through Paseo is not verified.
- The role configuration is an example only. The operator merges/reloads it and performs an actual Paseo launch; static checks do not establish that authentication or runtime integration works.
