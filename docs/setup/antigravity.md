# Antigravity Peer seat

This guide adds `agy-peer`, a Paseo Peer backed by Google's Antigravity CLI (`agy`) through the vendored ACP adapter. Paseo remains the only lifecycle/topology owner: `agy-acp` starts one `agy --print` subprocess per prompt; it does not spawn agents or run a daemon. Do not enable `agy remote-control`.

## Prerequisites and build

1. Install Google Antigravity CLI and ensure `agy` is on the PATH inherited by Paseo. Authenticate it using the supported `agy` login flow before launching a seat; authentication credentials remain in the CLI's user state, never in this repository.
2. Confirm `agy models` prints the configured model IDs. The example pins `gemini-3.1-pro-high` as default and also exposes `gemini-3.8-flash-high` and `claude-opus-4-6-thinking`.
3. Install Rust/Cargo, then build and install the checked-in adapter source:

   ```sh
   cd /path/to/epistex/tools/agy-acp
   cargo build --release
   install -m 755 target/release/agy-acp ~/.local/bin/agy-acp
   ```

   Ensure `~/.local/bin` is on Paseo's PATH. Cargo build output (`target/`) is ignored and must not be committed.

The vendored crate is sourced from `/home/linhlb/Downloads/agy-acp.zip`, SHA-256 `6cc6fe3622153eb9e373272485ac7f258350904feb5f94f853991a331e90f17d` (received 2026-10-08). Its `Cargo.lock`, README, and AGENTS instructions are retained alongside source for repeatable builds.

## Configure Paseo

Merge the `agy-peer` entry and its three model profiles from `examples/paseo-providers.json`; replace `<KIT>` with the absolute repository path. The provider extends `acp`, invokes `setup/role-agent peer agy`, and has Paseo tools disabled. Its `AGY_EXTRA_ARGS=--mode accept-edits` is needed so file edits can be approved in non-interactive print mode. This grants the adapter's agent edit-mode access to the project; do not replace it with `--dangerously-skip-permissions`, which auto-approves all tool permission requests. The adapter accepts additional `AGY_EXTRA_ARGS` as whitespace-separated arguments.

`agy-acp` inherits its initial working directory from its parent process; it does not use an ACP `session/new` cwd value. It passes that working directory to `agy` via `--add-dir` and sets it as the subprocess current directory. Ensure the Paseo launcher's process cwd is the intended workspace. This seat does not use `agy remote-control`.

## State and known limitations

The adapter keeps its session mapping under `~/.openab/agy-acp/sessions.json` and reads Antigravity conversation databases under `~/.gemini/antigravity-cli/conversations/`. These are private runtime state and must remain outside the repository. Do not edit or copy Antigravity settings or credentials into tracked files.

- ACP `session/cancel` is a no-op in this adapter; cancellation does not stop the current `agy` process.
- `agy --print` has a bridge-owned 24-hour timeout by default (`AGY_PRINT_TIMEOUT` overrides it). Long-running prompts may therefore occupy a turn for a substantial time.
- The role configuration is an example only. The operator merges/reloads it and performs an actual Paseo launch; static checks do not establish that authentication or runtime integration works.
