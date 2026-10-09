# Antigravity Peer seat

This guide adds `agy-peer`, a Paseo Peer backed by Google's Antigravity CLI (`agy`) through the vendored ACP adapter. Paseo remains the only lifecycle/topology owner: `agy-acp` starts one `agy --print` subprocess per prompt; it does not spawn agents or run a daemon. Do not enable `agy remote-control`.

## Prerequisites and build

1. Install Google Antigravity CLI and ensure `agy` is on the PATH inherited by Paseo. Authenticate it using the supported `agy` login flow before launching a seat; authentication credentials remain in the CLI's user state, never in this repository.
2. Confirm `agy models` prints the configured model IDs. The example pins `gemini-3.8-flash-low` as default and also exposes `gemini-3.8-flash-medium` and `gemini-3.8-flash-high`.
3. Install Rust/Cargo, then build and install the checked-in adapter source:

   ```sh
   cd /path/to/epistex/tools/agy-acp
   cargo build --release
   install -m 755 target/release/agy-acp ~/.local/bin/agy-acp
   ```

   Ensure `~/.local/bin` is on Paseo's PATH. Cargo build output (`target/`) is ignored and must not be committed.

The vendored crate is sourced from `/home/linhlb/Downloads/agy-acp.zip`, SHA-256 `6cc6fe3622153eb9e373272485ac7f258350904feb5f94f853991a331e90f17d` (received 2026-10-08). Its `Cargo.lock`, README, and AGENTS instructions are retained alongside source for repeatable builds.

## Configure Paseo

Merge the `agy-peer` entry and its three model profiles from `examples/paseo-providers.json`; replace `<KIT>` with the absolute repository path. The provider extends `acp`, invokes `setup/role-agent peer agy`, and has Paseo tools disabled. Its `AGY_EXTRA_ARGS=--mode accept-edits` selects Antigravity's accept-edits execution mode for non-interactive print turns. Do not describe this as file-edits-only: in the real Paseo probe, a shell `run_command` creating, reading and deleting a file executed without a permission prompt. `agy --help` lists `accept-edits` as a `--mode` value but does not specify the mode's detailed tool policy; the observed shell command establishes that it permits commands as well as file edits in this setup. Do not replace it with `--dangerously-skip-permissions`, which `agy --help` says auto-approves all tool permission requests. The adapter accepts additional `AGY_EXTRA_ARGS` as whitespace-separated arguments.

`agy-acp` inherits its initial working directory from its parent process; it does not use an ACP `session/new` cwd value. It passes that working directory to `agy` via `--add-dir` and sets it as the subprocess current directory. Paseo supplies the agent cwd as the adapter's process cwd; the real launch probe confirmed `pwd` inside the turn matched the agent cwd. This seat does not use `agy remote-control`.

## State and known limitations

The adapter keeps its session mapping under `~/.openab/agy-acp/sessions.json` and reads Antigravity conversation databases under `~/.gemini/antigravity-cli/conversations/`. These are private runtime state and must remain outside the repository. Do not edit or copy Antigravity settings or credentials into tracked files.

- ACP `session/cancel` sets the active prompt's cancellation flag (`tools/agy-acp/src/main.rs:121-130`). The adapter observes it, kills and waits for the direct `agy` child process, then reports `stopReason: "cancelled"` (`tools/agy-acp/src/adapter.rs:717-726, 806-814`). It does not erase the Antigravity conversation or roll back tool effects already made; if the conversation ID was bound, the adapter still updates and persists its session mapping. This stops the direct child, not necessarily any subprocesses it may have started. There is no cancellation-specific unit test in `tools/agy-acp/src/tests.rs`. The vendored `tools/agy-acp/AGENTS.md` still calls cancellation a no-op; that statement is stale relative to the implementation.
- **Fidelity limits:**
  - ACP text and thought updates are read by polling Antigravity's SQLite conversation DB every 500 ms (`tools/agy-acp/src/adapter.rs:701-714`), not by consuming `agy`'s native `stream-json` output. Updates can therefore lag the underlying action.
  - In the real Paseo probe, a `run_command` step executed but did not appear as a tool-call entry in Paseo's timeline, although thought and text streamed there.
  - ACP `session/new` does not consume its `cwd`; the adapter process cwd is used instead. Paseo supplied the agent cwd as process cwd in the probe (see Configure Paseo).
- `agy --print` has a bridge-owned 24-hour timeout by default (`AGY_PRINT_TIMEOUT` overrides it). Long-running prompts may therefore occupy a turn for a substantial time.
- The role configuration is an example only. The operator merges/reloads it and performs an actual Paseo launch; static checks do not establish that authentication or runtime integration works.
