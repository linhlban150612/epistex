# SETUP — Two separate Claude seats

Keep the contract/protocol and the backup, merge, MCP injection, reload and live verification steps
in [SETUP.md](../../SETUP.md) unchanged. Do not use `codex-room` for Claude.
Check `claude --version`, `claude auth status` and `paseo provider models claude --json` first.
Merge the two providers into `.agents.providers` with this configuration:

| Field | `claude-lead` | `claude-peer` |
|---|---|---|
| `extends` | `claude` | `claude` |
| `command` | `["<KIT>/setup/role-agent", "lead", "claude"]` | `["<KIT>/setup/role-agent", "peer", "claude"]` |
| `enabled` | `true` | `true` |
| `env` | `{"CLAUDE_CODE_AUTO_COMPACT_WINDOW":"200000"}` | same as `claude-lead` |
| `paseoTools.enabled` | `true` | `true`, Peer deny-list (every catalog tool blocked; [SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)) |
| `models[0].id` | `claude-opus-5-5` | `claude-sonnet-5-5` |
| `models[0].isDefault` | `true` | `true` |
| `models[0].thinkingOptions` | `[{"id":"low","label":"Low","isDefault":true}]` | `[{"id":"low","label":"Low","isDefault":true}]` |

Profile pins:

| Seat | Model | Thinking options |
|---|---|---|
| `claude-peer` | `claude-haiku-5-5` | `low`, `medium` |
| `claude-peer` | `claude-sonnet-5-5` | `low`, `medium` |
| `claude-peer` | `claude-opus-5-5` | `low`, `medium` |
| `claude-supervisor` | `claude-sonnet-5-5` (default) | `low` (default), `medium` |
| `claude-supervisor` | `claude-opus-5-5` | `low`, `medium` |
| `claude-supervisor` | `claude-fable-5-1` | `medium` (unverified: provider credits) |

`claude-supervisor` runs `role-agent supervisor claude`, with Paseo tools enabled.

Claude Lead uses the deny-list in [SETUP.md §3](../../SETUP.md); it does not apply to Peer.
The `claude-lead` profile and every `claude-peer` profile use `modeId: "bypassPermissions"`; `--check` rejects
a `claude-peer` profile without this mode. Live: with `acceptEdits`, a non-interactive Peer stops at a
Bash permission request when it runs `python3`/`git commit`; with `bypassPermissions` it does not.

Set the label/description by role and replace `<KIT>` with the absolute path. `role-agent` and
`claude-sdk` must be executable. `role-agent <role> claude` switches to the separate launcher
`setup/claude-sdk <role>` with `os.execv`, the same convention as `kiro-acp`. The launcher keeps the Paseo CWD and uses the existing Claude home/auth; it does not create two
Codex runtimes or change the canonical Claude settings. In the Claude SDK stream-json, the launcher
adds the role prompt to `request.appendSystemPrompt` of the `control_request` / `initialize` message,
and keeps the system prompt, the append text and the other SDK fields unchanged. The single CLI flag
`--append-system-prompt` is not sufficient: the `appendSystemPrompt` field in `initialize` replaces that flag.
A field in `initialize` replaces only the matching CLI flag; a flag without a matching field stays in effect.
Paseo sends `initialize` with `hooks`, `appendSystemPrompt`,
`forwardSubagentText`, `perTaskStopAffordance`, and sets `--model`, `--effort`, `--thinking`,
`--thinking-display`, `--permission-mode`, `--permission-prompt-tool stdio`, `--setting-sources`,
`--allow-dangerously-skip-permissions`, `--include-partial-messages` itself; do not add those flags to
`command`. Because `--allow-dangerously-skip-permissions` is always present, `set_agent_mode` can switch a
running seat to `bypassPermissions`. Paseo adds `--disallowedTools` only when the runtime settings have
a blocked tool; a normal launch has none. `claude-sdk` adds `--disallowed-tools` for `Agent`, `Task`,
`Workflow`, `CronCreate`, `CronDelete`, `CronList`, `ScheduleWakeup`, `RemoteTrigger`: Paseo manages
topology and the seat does not create schedules/heartbeats. Check the tool list with a real launch.

For the Peer seat only, `claude-sdk` adds `--settings` with one `PreToolUse` hook for `Bash`:
`setup/claude-guard`. The hook rejects (exit 2) three command forms: `rm` with recursive and force flags on a path
outside the workspace (`$CLAUDE_PROJECT_DIR`, or the Git top level of `cwd`; `/tmp/<x>` and
`/var/tmp/<x>` are allowed; a path with `$VAR` or `$(…)`, or a relative path after a `cd` the guard cannot follow, is rejected), `git push` with `--force`,
`-f`, `--force-with-lease`, `--mirror` or `+refspec`, and `git reset --hard`. If Paseo already passed
`--settings`, the launcher keeps that content and adds the hook; an unreadable value stops the launch.
This is a per-backend guard, not a sandbox: the hook matches the command text, in Claude only the Peer seat has
the hook (Droid Peer uses the same rule set `setup/seat_guard.py` through `setup/droid-guard`),
and it does not block hidden commands (script files, `xargs`, `find -delete`, other tools). All seats still run as the same
Unix user. A hook that cannot run denies nothing, so `setup-seats.sh --check` fails for an enabled
`claude-peer` when `setup/claude-guard` is not executable, does not allow `git status`, or does not
deny `git reset --hard` with exit 2. Check the hook with a real launch: ask Peer to run `git reset --hard` in a test repo.

After `paseo reload`, create a new session with the model, `thinking=low` and the mode from discovery.
Ask the agent to print the role heading **from the active system instructions**; do not let it read the prompt file
as a substitute for evidence. Lead must have the heading `# Lead — Project Lead & binding technical arbiter`,
see Paseo tools and be able to call one read-only tool; Peer must have the heading
`# Peer — independent co-worker` and must not see Paseo tools, also through deferred tool discovery.
Lead coordinates Claude Peers with `claude-peer`, not with the original Claude provider.

`setup-seats.sh --check` checks the supervisor seats. Check the provider fields and run real launches for the roles.
This is role/MCP separation, not an OS sandbox or two isolated credential homes.
