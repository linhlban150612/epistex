# SETUP — Paseo role seats

Điểm vào chung: bước 1–8 cài hai seat Codex (Lead/Peer) và kiểm launch thật. Mỗi backend khác
dùng lại các bước chung này, rồi theo file riêng:

| Backend | Hướng dẫn |
|---|---|
| Claude Lead/Peer | [docs/setup/claude.md](docs/setup/claude.md) |
| Amp Lead/Peer qua ACP | [docs/setup/amp.md](docs/setup/amp.md) |
| Pi Peer, OMP Peer | [docs/setup/pi-omp.md](docs/setup/pi-omp.md) |
| Devin Supervisor/Lead/Peer, Copilot Peer, Cursor Peer qua ACP | [docs/setup/devin-copilot-cursor.md](docs/setup/devin-copilot-cursor.md) |

## 1. Đặt kit và project ở đường dẫn ổn định

`<KIT>` là đường dẫn tuyệt đối tới thư mục `epistex`; `<PROJECT>` là repository mà các seat làm
việc. Paseo daemon phải chạy dưới đúng user sở hữu Codex home và project. Mặc định provider dùng
working directory của workspace Paseo; chỉ đặt `EPISTEX_PROJECT_ROOT` để cố định provider vào một
project, không giữ đường dẫn repo cũ. Codex chạy tại launcher/worktree CWD; thư mục con và linked
worktree của cùng repo Git dùng chung runtime, còn ngoài Git mỗi CWD tuyệt đối là một project riêng.

Session tạo từ thư mục con/worktree/project khác chỉ resume được bằng UUID tường minh
(`codex resume <UUID>`, `codex exec resume <UUID>`, alias `e resume <UUID>`; options đặt sau UUID).
Picker, tên session, `--last` và app-server chỉ thấy runtime của project hiện tại. Quy tắc chọn
runtime theo UUID: [README.md § Codex runtime and resume](README.md#codex-runtime-and-resume).

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
`claude-peer` theo [docs/setup/claude.md](docs/setup/claude.md). Thiếu một lane thì Lead báo
`BLOCKED`, không chạy một lane hay đổi backend.

Linux Desktop: nếu `paseo` là symlink tới `/opt/Paseo/Paseo` và `paseo run` mở GUI, dùng launcher
đi kèm `/opt/Paseo/resources/bin/paseo` cho các lệnh CLI; không cần đổi symlink hay restart daemon.

## 3. Bật injection Paseo tools

Trong `~/.paseo/config.json`, bảo đảm:

```json
{"daemon":{"mcp":{"enabled":true,"injectIntoAgents":true}}}
```

Quyền theo role nằm ở provider: Lead đặt `paseoTools.enabled=true`, Peer đặt `false`. Không
dùng `injectIntoProviders`; field đó không phải cơ chế policy provider hiện hành.

### Chính sách 13 Paseo tools cho Lead/Supervisor

Provider bật Paseo dùng `paseoTools.disabledTools` để chặn catalog, giữ đúng 13 tool: `list_agents`,
`list_workspaces`, `list_providers`, `list_models`, `create_agent`, `send_agent_prompt`,
`get_agent_activity`, `get_agent_status`, `cancel_agent`, `archive_agent`,
`list_pending_permissions`, `respond_to_permission`, `set_agent_mode`. Các nhóm bị chặn: 11
schedule/heartbeat, 22 browser, 5 terminal, 10 workspace/agent/provider (xem danh sách trong
[ví dụ provider](examples/paseo-providers.json)). Cần Paseo ≥ 0.10.3; đã xác minh trên 0.11.0.
`speak` không thể bị chặn và nằm ngoài catalog. Test pin catalog 61 tên để buộc review khi nâng
cấp Paseo. Script `--check` xác nhận deny-list chính xác trên mọi provider đang bật.

## 4. Merge provider seats

Sao lưu config, rồi merge ba entry trong `examples/paseo-providers.json` vào `.agents.providers`
của file Paseo hiện có; không thay cả file, giữ nguyên provider khác và cấu hình daemon. Trước khi
merge: thay `<KIT>` bằng đường dẫn tuyệt đối tới `epistex`; nếu cần cố định project, thêm
`env.EPISTEX_PROJECT_ROOT` tuyệt đối; xóa `_doc`; xác nhận model ID bằng
`paseo provider diagnostic codex --json` hoặc provider discovery. Mẫu chọn Lead `gpt-6.1-sol` và
Peer `gpt-6-luna`, effort mặc định `low`. `command` phải giữ đúng role `lead` và `peer`.

## 5. Đặt contract và protocol tại project đích

- Dùng `examples/AGENTS_MD_SNIPPET.md` để bổ sung contract chung mà cả Lead và Peer đọc.
- Copy `examples/WORKSPACE_PROTOCOL.md` thành `<PROJECT>/WORKSPACE_PROTOCOL.md`, rồi điền risk,
  authority, task class và review gate riêng của repo. File này dành cho Lead; Peer nhận phần
  constraint cần thiết qua task brief.

Trước khi commit hai file trên, tuân theo hygiene của repo đích. Nếu repo cấm persona/process
document, giữ `WORKSPACE_PROTOCOL.md` local và ignored (hoặc ở vị trí Human quản lý), còn
`AGENTS.md` chỉ chứa product boundary, invariant, canonical docs và verification có giá trị bền.
Không tạo evidence folder, review packet hay status ledger trong Git. Không nhét policy riêng của
repo vào provider Paseo hoặc prompt Peer.

## 6. Dựng và kiểm

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s <KIT>/tests
bash <KIT>/setup/setup-seats.sh
paseo reload
bash <KIT>/setup/setup-seats.sh --check
```

Script không tự sửa global config; lượt không có `--check` chỉ đặt executable bit (cần chmod),
runtime được chuẩn bị khi Paseo khởi động seat. `--check` thất bại nếu config/provider thiếu hoặc
sai model, effort hay quyền tools; nó cần Bash, jq, Python 3.11+, dirname, wc và
`${CODEX_BIN:-codex}`, không cần Paseo trên PATH. `PASEO_HOME`/`PASEO_CONFIG` chọn config khác vị
trí mặc định; nếu dùng `CODEX_BIN`, đặt cùng giá trị cho checker và các provider. Kết quả hợp lệ
không chứng minh auth, daemon, model khả dụng hay launch thành công: đó là bước 2 và bước 7.

## 7. Chứng minh cô lập

Khởi động một agent `codex-peer`, yêu cầu nó in dòng đầu prompt role đang đọc; kết quả phải là
`# Peer — independent co-worker`. Làm tương tự với `codex-lead`, kết quả bắt đầu bằng `# Lead`.
Kiểm thêm `find ~/.codex-runtime/epistex -maxdepth 3 -name config.toml`.

Hai role phải có runtime riêng. `auth.json`, `skills`, `plugins` là symlink; `config.toml` là bản
generated riêng chứa `model_instructions_file` trỏ về prompt trong kit, với `[agents].enabled`,
`[features].multi_agent` và `[features].multi_agent_v2` đều `false`: Paseo là chủ duy nhất của
topology. TOML không hợp lệ hoặc sai kiểu bảng policy làm launch thất bại trước khi đổi runtime.
Bản generated dùng inline tables, không giữ comment/format, giữ nguyên giá trị ngoài policy (kể cả
chuỗi nhiều dòng); file canonical không bị sửa. Sync không xóa private state, từ chối runtime hoặc
thư mục cha là symlink; chỉ thay `config.toml` là atomic, lỗi I/O hoặc thay đổi đồng thời có thể để
lại một phần links đã đổi (chi tiết: [README.md](README.md#codex-runtime-and-resume)).

Đây là tách state và quyền MCP, không phải sandbox chống agent độc hại: các role chạy cùng Unix
user, chia sẻ skills/plugins và vẫn có shell. Peer bị cấm gọi Paseo theo prompt; việc ẩn Paseo MCP
không ngăn tuyệt đối một shell gọi CLI.

## 8. Vận hành

Lead luôn tạo Peer bằng provider role (`codex-peer` hoặc provider `*-peer` trong `docs/setup/`);
không dùng provider backend gốc. Truyền rõ `modeId` và `thinkingOptionId` khi tạo agent. Agent đang
chạy không tự nhận thay đổi provider; sau khi sửa `~/.paseo/config.json`, chạy `paseo reload` và
tạo phiên mới. Prompt trong kit có trần kỷ luật 16 KiB; sửa xong chạy lại `setup-seats.sh --check`.
