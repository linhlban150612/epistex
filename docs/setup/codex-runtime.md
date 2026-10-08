# Codex runtime, resume, and environment

This guide documents Codex runtime selection, resume behavior, environment compatibility, and
project prerequisites. Backend-specific seat setup remains in the linked
[backend guides](.).

## Codex runtime and resume

```text
Paseo provider → setup/codex-room <role> → setup/codex-room-sync
  → ~/.codex-runtime/epistex/<project-id>/<role>/
       config.toml          generated, role prompt
       auth.json            → canonical Codex home
       skills/, plugins/    → canonical Codex home
       sessions/logs/...    private mutable state
  → Codex at the wrapper-selected working directory
```

Git root, subdirectories, and linked worktrees share role runtime through the shared Git directory;
the usual `.git` layout retains the old main-checkout path hash. Outside Git (or when Git is
unavailable), identity is based on the absolute path. If set, `EPISTEX_PROJECT_ROOT` selects both
the project and launch CWD; otherwise, the launcher's `$PWD` is used.

Sync links shared resources from the canonical home, parses/round-trips TOML, applies the prompt,
and disables `agents.enabled`, `features.multi_agent`, and `features.multi_agent_v2`. For Peer, it
removes the MCP server named `paseo` from runtime config. Canonical config is not modified. Sync
preserves private sessions/logs/database, rejects runtime or ancestor symlinks, and preflights
conflicts; **only replacing `config.toml` is atomic**, not the entire link update.

UUID resume can find the same-role runtime in both the `epistex` and `seatworks` namespaces; it
does not copy the session:

```bash
setup/codex-room peer exec resume '<session-UUID>' --json 'Continue the assigned task'
```

Use the UUID immediately after `resume`, and put options after the UUID, not before the command or
UUID; the `e resume <UUID>` alias is also supported. If there are zero or multiple matching
runtimes, stop. Picker, session name, `--last`, and other layout arguments use only the current
project runtime. The wrapper **does not read session IDs from app-server RPC**; changing CLI
routing does not prove that an old Supervisor in Paseo can resume.

### Environment variables and Seatworks compatibility

| Variable | Default / purpose |
|---|---|
| `EPISTEX_PROJECT_ROOT` | Launcher CWD for Codex when the project must be pinned |
| `EPISTEX_CODEX_HOME` | `~/.codex`; canonical config and shared-resource source |
| `CODEX_BIN` | Codex executable; defaults to looking up `codex` on PATH |
| `PASEO_CONFIG` | Config file used by the seat checker |
| `PASEO_HOME` | Seat checker uses `<PASEO_HOME>/config.json` if `PASEO_CONFIG` is unset |

`SEATWORKS_PROJECT_ROOT` and `SEATWORKS_CODEX_HOME` are fallbacks for their corresponding
`EPISTEX_*` variables; a non-empty new value takes precedence. An old runtime under
`.codex-runtime/seatworks` is used in place if it is the sole match for project/role. If both old
and new runtimes exist, ordinary launch reports ambiguity. There is no bulk migration; do not
delete/copy data to fix resume.


## Project paths and runtime prerequisites

## 1. Đặt kit và project ở đường dẫn ổn định

`<KIT>` là đường dẫn tuyệt đối tới thư mục `epistex`; `<PROJECT>` là repository mà các seat làm
việc. Paseo daemon phải chạy dưới đúng user sở hữu Codex home và project. Mặc định provider dùng
working directory của workspace Paseo; chỉ đặt `EPISTEX_PROJECT_ROOT` để cố định provider vào một
project, không giữ đường dẫn repo cũ. Codex chạy tại launcher/worktree CWD; thư mục con và linked
worktree của cùng repo Git dùng chung runtime, còn ngoài Git mỗi CWD tuyệt đối là một project riêng.

Session tạo từ thư mục con/worktree/project khác chỉ resume được bằng UUID tường minh
(`codex resume <UUID>`, `codex exec resume <UUID>`, alias `e resume <UUID>`; options đặt sau UUID).
Picker, tên session, `--last` và app-server chỉ thấy runtime của project hiện tại. Quy tắc chọn
runtime theo UUID: [Codex runtime and resume](#codex-runtime-and-resume).

## 2. Kiểm tiền đề

```bash
bash --version
python3 --version # cần 3.11+ để kiểm TOML
jq --version
codex --version
paseo daemon status --json
```

Codex home chuẩn mặc định là `~/.codex`; nếu credential/config thật nằm nơi khác, khai
`EPISTEX_CODEX_HOME` trong `env` của các Codex provider. Biến cũ `SEATWORKS_PROJECT_ROOT`,
`SEATWORKS_CODEX_HOME` vẫn được đọc; biến `EPISTEX_*` tương ứng luôn ưu tiên. Runtime cũ dưới
`~/.codex-runtime/seatworks` chỉ được dùng tại chỗ khi là kết quả duy nhất phù hợp; không có
migration, dữ liệu cũ không bị xóa; nhiều runtime cũ/mới cùng phù hợp thì launch dừng.

Dual-Lane review (task class complex/review) cần cả `claude-peer` lẫn `codex-peer`; cài thêm
`claude-peer` theo [Claude setup](claude.md). Thiếu một lane thì Lead báo
`BLOCKED`, không chạy một lane hay đổi backend.

Linux Desktop: nếu `paseo` là symlink tới `/opt/Paseo/Paseo` và `paseo run` mở GUI, dùng launcher
đi kèm `/opt/Paseo/resources/bin/paseo` cho các lệnh CLI; không cần đổi symlink hay restart daemon.

### Key files

| Path | Role |
|---|---|
| `agents/*.md` | Supervisor, Lead, and Peer prompts |
| `setup/role-agent` | Native Claude/Pi launcher and ACP instruction proxy |
| `setup/codex-room`, `setup/codex-room-sync` | Select runtime/resume and generate Codex config |
| `setup/setup-seats.sh`, `examples/paseo-providers.json` | Three role seats and provider check |
| `SETUP.md` | Setup entry point: common steps, Codex seats, live verification |
| `docs/setup/*.md` | Backend-specific seats: Claude, Amp, Pi/OMP, Devin/Copilot/Cursor |
| `examples/AGENTS_MD_SNIPPET.md`, `examples/WORKSPACE_PROTOCOL.md` | Contract/policy templates for target repos |
| `tests/` | Runtime, role launcher, and seat-checker regression tests |
