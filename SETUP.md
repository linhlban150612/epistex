# SETUP — Paseo role seats

Điểm vào chung: bước 1–8 cài hai seat Codex (Lead/Peer) và kiểm launch thật. Mỗi backend khác
dùng lại các bước chung này, rồi theo file riêng:

Chi tiết chọn project/runtime và tiền đề: [hướng dẫn runtime Codex](docs/setup/codex-runtime.md)
(các bước 1–2).

| Backend | Hướng dẫn |
|---|---|
| Claude Lead/Peer | [docs/setup/claude.md](docs/setup/claude.md) |
| Amp Lead/Peer qua ACP | [docs/setup/amp.md](docs/setup/amp.md) |
| Antigravity Peer qua ACP | [docs/setup/antigravity.md](docs/setup/antigravity.md) |
| Pi Peer, OMP Peer | [docs/setup/pi-omp.md](docs/setup/pi-omp.md) |
| Devin Supervisor/Lead/Peer, Copilot Peer, Cursor Peer qua ACP | [docs/setup/devin-copilot-cursor.md](docs/setup/devin-copilot-cursor.md) |

Context compaction và giới hạn từng backend: [context-compaction.md](docs/setup/context-compaction.md).

## 1. Đặt kit và project ở đường dẫn ổn định

Đặt kit và project ở đường dẫn tuyệt đối, ổn định; Paseo daemon phải chạy dưới đúng user. Chi tiết
project root và runtime: [Codex runtime](docs/setup/codex-runtime.md#project-paths-and-runtime-prerequisites).

## 2. Kiểm tiền đề

Xác nhận Bash, Python 3.11+, `jq`, Codex và Paseo daemon; kiểm credentials/backend theo
[chi tiết tiền đề và tương thích](docs/setup/codex-runtime.md#project-paths-and-runtime-prerequisites).

## 3. Bật injection Paseo tools

Trong `~/.paseo/config.json`, bảo đảm:

```json
{"daemon":{"mcp":{"enabled":true,"injectIntoAgents":true}}}
```

Quyền theo role nằm ở provider: Lead đặt `paseoTools.enabled=true`, Peer đặt `false`. Không
dùng `injectIntoProviders`; field đó không phải cơ chế policy provider hiện hành.

### Chính sách Paseo tools cho Lead và Supervisor

Lead dùng `paseoTools.disabledTools` để chặn catalog, giữ đúng 14 tool: `list_agents`,
`list_workspaces`, `list_providers`, `list_models`, `list_profiles`, `create_agent`, `send_agent_prompt`,
`get_agent_activity`, `get_agent_status`, `cancel_agent`, `archive_agent`,
`list_pending_permissions`, `respond_to_permission`, `set_agent_mode`. Supervisor giữ thêm `create_workspace` (15 tool được giữ; 46 bị chặn), còn Lead giữ 14 tool (47 bị chặn).
Các nhóm bị chặn ở Lead: 11 schedule/heartbeat, 22 browser, 5 terminal, 9 workspace/agent/provider;
ở Supervisor nhóm workspace/agent/provider còn 8 (xem danh sách trong
[ví dụ provider](examples/paseo-providers.json)). Cần Paseo 0.11.1; daemon và CLI cùng phiên bản.
`speak` không thể bị chặn và nằm ngoài catalog. Test pin catalog 61 tên để buộc review khi nâng
cấp Paseo. Script `--check` xác nhận deny-list chính xác trên mọi provider đang bật.

## 4. Merge provider seats

Sao lưu config, rồi merge `agents.providers` và `daemon.agentProfiles` trong `examples/paseo-providers.json`
vào các phần tương ứng của file Paseo hiện có; không thay cả file, giữ nguyên provider khác và cấu hình daemon. Trước khi
merge: thay `<KIT>` bằng đường dẫn tuyệt đối tới `epistex`; nếu cần cố định project, thêm
`env.EPISTEX_PROJECT_ROOT` tuyệt đối; xóa `_doc`; xác nhận model ID bằng
`paseo provider diagnostic codex --json` hoặc provider discovery. Mẫu chọn Lead `gpt-6.1-sol` và
Peer `gpt-6-luna`, effort mặc định `low`. `command` phải giữ đúng role `lead` và `peer`.

## 5. Paseo agent profiles

`examples/paseo-providers.json` chứa inventory dưới `daemon.agentProfiles`, đúng như live config. ID dùng
mẫu `<seat>--<model-slug>--<thinking>`; profile không chứa prompt. Orchestrator sao chép `provider`,
`model` và `thinkingOptionId` khi gọi `create_agent`; Lead/Supervisor khám phá inventory bằng
`list_profiles`. Amp profiles không có thinking option khi model không khai báo options. Cả daemon và
CLI đang ở Paseo 0.11.1. Sau sửa config, `paseo reload` trả `Configuration reloaded.` trong lần
kiểm chứng này. Xác minh phiên mới/launch riêng; reload output không tự chứng minh model hoặc role.

## 6. Đặt contract và protocol tại project đích

- Dùng `examples/AGENTS_MD_SNIPPET.md` để bổ sung contract chung mà cả Lead và Peer đọc.
- Copy `examples/WORKSPACE_PROTOCOL.md` thành `<PROJECT>/WORKSPACE_PROTOCOL.md`, rồi điền risk,
  authority, task class và review gate riêng của repo. File này dành cho Lead; Peer nhận phần
  constraint cần thiết qua task brief.

Trước khi commit hai file trên, tuân theo hygiene của repo đích. Nếu repo cấm persona/process
document, giữ `WORKSPACE_PROTOCOL.md` local và ignored (hoặc ở vị trí Human quản lý), còn
`AGENTS.md` chỉ chứa product boundary, invariant, canonical docs và verification có giá trị bền.
Không tạo evidence folder, review packet hay status ledger trong Git. Không nhét policy riêng của
repo vào provider Paseo hoặc prompt Peer.

## 7. Dựng và kiểm

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s <KIT>/tests
bash <KIT>/setup/setup-seats.sh
paseo reload
bash <KIT>/setup/setup-seats.sh --check
```

Script không tự sửa global config; lượt không có `--check` chỉ đặt executable bit (cần chmod),
runtime được chuẩn bị khi Paseo khởi động seat. `--check` thất bại nếu config/provider thiếu hoặc
sai model, effort hay quyền tools; nó cần Bash, jq, Python 3.11+, dirname, wc, grep và
`${CODEX_BIN:-codex}`, không cần Paseo trên PATH. `PASEO_HOME`/`PASEO_CONFIG` chọn config khác vị
trí mặc định; nếu dùng `CODEX_BIN`, đặt cùng giá trị cho checker và các provider. Kết quả hợp lệ
không chứng minh auth, daemon, model khả dụng hay launch thành công: đó là bước 2 và bước 7.

## 8. Chứng minh cô lập

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
lại một phần links đã đổi (chi tiết: [Codex runtime and resume](docs/setup/codex-runtime.md#codex-runtime-and-resume)).

Đây là tách state và quyền MCP, không phải sandbox chống agent độc hại: các role chạy cùng Unix
user, chia sẻ skills/plugins và vẫn có shell. Peer bị cấm gọi Paseo theo prompt; việc ẩn Paseo MCP
không ngăn tuyệt đối một shell gọi CLI.


## 9. Vận hành

Lead luôn tạo Peer bằng provider role (`codex-peer` hoặc provider `*-peer` trong `docs/setup/`);
không dùng provider backend gốc. Truyền rõ `modeId` và `thinkingOptionId` khi tạo agent. Agent đang
chạy không tự nhận thay đổi provider; sau khi sửa `~/.paseo/config.json`, chạy `paseo reload` và
tạo phiên mới. Prompt trong kit có trần kỷ luật 16 KiB; sửa xong chạy lại `setup-seats.sh --check`.
