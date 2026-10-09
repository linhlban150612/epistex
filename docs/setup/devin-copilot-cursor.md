# SETUP — Devin Lead/Peer, Supervisor, GitHub Copilot Peer và Cursor Peer qua ACP

Dùng các bước backup, merge, MCP injection, contract/protocol, reload và live verification
trong [SETUP.md](../../SETUP.md).

Supervisor là observer Paseo-only, cấu hình dưới provider `devin-supervisor` với command
`["<KIT>/setup/role-agent","supervisor","devin"]`. Không pin CWD bằng env: workspace
`~/work/SUPERVISOR` phải để trống; `agents/SUPERVISOR.md` xác nhận CWD chính xác rồi
khám phá workspace/agent/provider/model qua Paseo. Supervisor mở Lead cross-workspace bằng
`create_agent(workspaceId=...)`, đưa agentId của mình vào initialPrompt để Lead hỏi qua
`send_agent_prompt`. Supervisor không tạo Peer, không ghi artifact và không nhận thay Lead.
Chỉ khi có event (notification, câu hỏi của Lead, yêu cầu của Human) Supervisor mới được dùng
`list_pending_permissions`, `respond_to_permission`, `cancel_agent`, `set_agent_mode`, rồi báo
Lead sở hữu; không quét agent, không kiểm định kỳ.

Backup và merge vào `.agents.providers`, không thay các backend gốc hay credential/config
home của chúng. Kiểm executable, auth và discovery của `devin`, `copilot`, `cursor` trước.
Giữ MCP injection bật ở daemon; Supervisor và Devin Lead expose Paseo tools.

| Provider | `command` (thay `<KIT>` bằng đường dẫn tuyệt đối) | Model ID | Thinking mặc định | Paseo tools |
|---|---|---|---|---|
| `devin-supervisor` | `["<KIT>/setup/role-agent","supervisor","devin"]` | `fusion-claude-fable-5-1-medium-sidekick-swe-2-medium` | `medium` | Bật |
| `devin-lead` | `["<KIT>/setup/role-agent","lead","devin"]` | `fusion-claude-fable-5-1-medium-sidekick-swe-2-medium` | `medium` | Bật |
| `devin-peer` | `["<KIT>/setup/role-agent","peer","devin"]` | `fusion-claude-opus-5-5-high-sidekick-swe-2-medium` (mặc định), `swe-2-high` | `high` | Tắt |
| `copilot-peer` | `["<KIT>/setup/role-agent","peer","copilot"]` | `gpt-6-luna` | `medium` | Tắt |
| `cursor-peer` | `["<KIT>/setup/role-agent","peer","cursor"]` | `composer-2.5[fast=true]` | Không có | Tắt |

Additional supervisor pins:

| Seat | Launcher args | Model | Thinking/profile pins |
|---|---|---|---|
| `codex-supervisor` | `codex-room supervisor` | `gpt-6-astra` | low, medium |
| `claude-supervisor` | `role-agent supervisor claude` | `claude-fable-5-1` | medium (unverified: provider credits) |
| `amp-supervisor` | `role-agent supervisor amp` | `medium`, `high` | no thinking options |

`copilot-peer` profiles pin each of Gemini 3.8 Flash, Kimi K3, Claude Haiku 5.5, Grok 4.7, and Claude Sonnet 5.5 at low and medium.

Devin Lead và Supervisor dùng deny-list tại [SETUP.md §3](../../SETUP.md).

Cả năm entry dùng `extends: "acp"`, `enabled: true`, `env: {}` và `paseoTools.enabled`
theo bảng. Đặt `models: [{"id":"<MODEL>","label":"<LABEL>","isDefault":true}]`; với
Devin/Copilot thêm `thinkingOptions: [{"id":"<EFFORT>","label":"<LABEL>","isDefault":true}]`
vào model theo bảng. Không thêm thinking option cho Composer 2.5.

ID rút gọn `fusion-claude-fable` không xuất hiện trong discovery tại lần cài này; ID đầy đủ
ở bảng đúng tên Fusion (Claude Fable 5.1 Medium + SWE-2 Medium). Discovery summary báo
Devin effort mặc định `medium`, nhưng phiên Fusion Opus High thực tế báo `high`; giữ `high`
để khớp biến thể được yêu cầu. Cursor summary trả ID trần `composer-2.5`, nhưng ACP session
catalog/set-model yêu cầu `composer-2.5[fast=true]`; ID trần bị từ chối và phiên đầu vẫn ở
`default[]`. Kiểm lại catalog của phiên và metadata sau launch, không chỉ discovery summary.

Launcher chạy `devin acp`, `copilot --acp`, `cursor-agent acp`; dùng proxy ACP hiện có để
thêm role instructions vào prompt đầu tiên của mỗi session, không phải system prompt.
Không thêm project policy vào provider hoặc sửa global instructions của backend.
Sau reload, tạo phiên mới với model/effort và mode thực tế từ discovery. ACP hiện trả Devin
mode `accept-edits`, Copilot `https://agentclientprotocol.com/protocol/session-modes#agent`,
Cursor `agent` cho phiên smoke test; không suy ra mode ID `default` từ nhãn/default summary.

Kiểm heading role từ context agent thực sự nhận, CWD bằng `pwd`, model/effort và inventory
kể cả deferred discovery nếu có. Devin Lead phải gọi thành công một Paseo MCP tool read-only;
các Peer không thấy Paseo tools. Không dùng shell CLI thay bằng chứng MCP. Không bật delegation
trong smoke test. Native tool/subagent của backend không đồng nghĩa với Paseo MCP; role/tool
visibility không phải OS sandbox. Checker Codex và diagnostic không thay thế live verification
của các seat này.

Nếu Cursor trả `Upgrade your plan to continue` sau khi metadata đã chọn đúng Composer,
đó chưa phải phiên smoke test thành công. Giữ model yêu cầu, báo giới hạn tài khoản và kiểm
lại sau khi Human xử lý quyền sử dụng; không tự chuyển Auto hay nâng cấp gói để vượt lỗi.
