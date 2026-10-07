# SETUP — Paseo role seats

Điểm vào chung: bước 1–8 cài hai seat Codex (Lead/Peer) và kiểm launch thật. Mỗi backend khác
dùng lại các bước chung này, rồi theo file riêng:

Chi tiết chọn project/runtime, tiền đề và kiểm cô lập nằm trong [hướng dẫn runtime Codex](docs/setup/codex-runtime.md) (các bước 1, 2, 7).

| Backend | Hướng dẫn |
|---|---|
| Claude Lead/Peer | [docs/setup/claude.md](docs/setup/claude.md) |
| Amp Lead/Peer qua ACP | [docs/setup/amp.md](docs/setup/amp.md) |
| Pi Peer, OMP Peer | [docs/setup/pi-omp.md](docs/setup/pi-omp.md) |
| Devin Supervisor/Lead/Peer, Copilot Peer, Cursor Peer qua ACP | [docs/setup/devin-copilot-cursor.md](docs/setup/devin-copilot-cursor.md) |

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

## 8. Vận hành

Lead luôn tạo Peer bằng provider role (`codex-peer` hoặc provider `*-peer` trong `docs/setup/`);
không dùng provider backend gốc. Truyền rõ `modeId` và `thinkingOptionId` khi tạo agent. Agent đang
chạy không tự nhận thay đổi provider; sau khi sửa `~/.paseo/config.json`, chạy `paseo reload` và
tạo phiên mới. Prompt trong kit có trần kỷ luật 16 KiB; sửa xong chạy lại `setup-seats.sh --check`.
