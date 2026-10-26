# SETUP — Hai seat Amp riêng qua ACP

Dùng các bước backup, merge, MCP injection, contract/protocol, reload và live verification
trong [SETUP.md](../../SETUP.md). Cần executable `amp-acp` và tài khoản Amp đã đăng nhập.
Kiểm discovery bằng `paseo provider models amp-acp --json` và `paseo provider diagnostic amp-acp --json`.
Adapter có thể không hỗ trợ `--version`; diagnostic ACP initialize/session mới và launch
thực tế là kiểm tra riêng, không coi lỗi version command là bằng chứng launch thất bại.

Merge hai provider vào `.agents.providers`, không thay provider `amp-acp` hiện có:

| Field | `amp-lead` | `amp-peer` |
|---|---|---|
| `extends` | `acp` | `acp` |
| `command` | `["<KIT>/setup/role-agent", "lead", "amp"]` | `["<KIT>/setup/role-agent", "peer", "amp"]` |
| `enabled` | `true` | `true` |
| `env` | `{}` | `{}` |
| `paseoTools.enabled` | `true` | `false` |
| `models[0].id` | `medium` | `low` |
| `models[0].label` | `Medium` | `Low` |
| `models[0].isDefault` | `true` | `true` |

`amp-supervisor` dùng `role-agent supervisor amp`, model `medium`/`high`, tools bật; không có thinking options.

Amp Lead dùng deny-list tại [SETUP.md §3](../../SETUP.md); không áp dụng cho Peer.

`medium`/`low` ở đây là model ID mà Amp ACP expose qua Paseo, không phải thinking option
riêng. Không thêm `thinkingOptions` giả.

Profile pins:

| Seat | Model | Profile pins | Thinking options |
|---|---|---|---|
| `amp-lead` | `medium` | `amp-lead--medium` | Không có |
| `amp-peer` | `low` | `amp-peer--low` | Không có |
| `amp-supervisor` | `medium`, `high` | `amp-supervisor--medium`, `amp-supervisor--high` | Không có |

Chọn permission mode từ discovery (amp-acp v0.10.0 chỉ có `local` và `orb`, không có mode bypass);
`amp-lead--medium` dùng `local`. Thay `<KIT>` bằng đường dẫn tuyệt
đối, giữ `role-agent` executable, rồi chạy `paseo reload` và tạo phiên mới.

ACP proxy thêm role instructions vào prompt đầu tiên của mỗi session trong vòng đời proxy,
không phải system prompt. Kiểm heading Lead/Peer từ nội dung session agent thực sự nhận,
CWD thực tế và tool inventory: Lead phải gọi được một Paseo tool read-only; Peer không thấy
Paseo tools. Không yêu cầu agent đọc file prompt rồi coi đó là proof injection.
Lead điều phối bằng `amp-peer`, không dùng provider Amp gốc.

Live E2E (2026-10-25, Amp `0.0.1792886472`, Paseo 0.13.0): `amp-peer` low launch qua Paseo, CWD là
project, không thấy tool Paseo. Amp bọc prompt dưới heading `# Instructions` của riêng nó; heading role
`# Peer — independent co-worker` vẫn đến nguyên vẹn. Catalog native có `Task`/`create_thread`
(subagent của Amp); đây không phải Paseo MCP.

`setup-seats.sh --check` xác nhận supervisor launcher, tools và pin model. Profile inventory gồm Amp Lead medium, Amp Peer low và Supervisor medium/high. Kiểm riêng hai Amp provider và live launch;
không thay global Amp config, credentials hoặc state để tạo role separation.
