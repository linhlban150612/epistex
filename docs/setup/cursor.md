# SETUP — Cursor Supervisor, Lead và Peer qua ACP

Dùng các bước chung trong [SETUP.md](../../SETUP.md), gồm mục
[ACP proxy seats](../../SETUP.md#acp-proxy-seats). Kiểm executable, auth và discovery của `cursor-agent` trước.

| Field | `cursor-supervisor` | `cursor-lead` | `cursor-peer` |
|---|---|---|---|
| `command` | `["<KIT>/setup/role-agent","supervisor","cursor"]` | `[…,"lead","cursor"]` | `[…,"peer","cursor"]` |
| `paseoTools` | 15 tool Supervisor | 8 tool Lead | `enabled: false` |
| `models` (đầu tiên là default) | `grok-4.7-medium-500k`; `grok-4.7-high-500k` | `gemini-4-carbon-medium`; `gemini-4-carbon-high` | `composer-2.5`; `grok-4.7-low`; `grok-4.7-medium` |
| `thinkingOptions` | Không có; launcher chuyển model ID thành tham số ACP | như bên trái | như bên trái |
| Profile pin | `cursor-supervisor--grok-4-7-medium-500k`, `--grok-4-7-high-500k` | `cursor-lead--gemini-4-carbon-medium`, `--high` | `cursor-peer--composer-2-5`, `--grok-4-7-low`, `--grok-4-7-medium` |
| `modeId` | `agent` | `agent` | `agent` (`plan`/`ask` không ghi file) |

`--check` kiểm launcher, tool, đúng danh sách model, default và đủ profile với `modeId: agent` cho mỗi seat đang bật.
`role-agent <role> cursor` chuyển sang `setup/cursor-acp <role>` bằng `os.execv`; launcher chạy
`cursor-agent acp`. Các ID trên là ID của seat, không phải ID gửi trực tiếp cho Cursor ACP.

| Seat model ID | `model` | `reasoning_effort` | `context` | `fast` |
|---|---|---|---|---|
| `grok-4.7-medium-500k`, `grok-4.7-high-500k` | `grok-4.7` | `medium`, `high` | `500k` | `false` |
| `gemini-4-carbon-medium`, `gemini-4-carbon-high` | `gemini-4-carbon` | `medium`, `high` | không có | không có |
| `composer-2.5` | `composer-2.5` | không có | không có | `false` |
| `grok-4.7-low`, `grok-4.7-medium` | `grok-4.7` | `low`, `medium` | `256k` | `false` |

Mỗi role chỉ chọn được model của role đó; launcher từ chối model của role khác.

## Tool Paseo của Lead và Supervisor

Cursor ACP chỉ có mode `agent`, `plan`, `ask`; không có bypass mode. Không có cấu hình thêm, Lead và
Supervisor dừng ở permission request tại mỗi lần gọi tool Paseo (kiểm live). Launcher thêm token
`Mcp(paseo:<tool>)` vào `permissions.allow` cho đúng các tool Paseo role đó giữ (Lead 8 cộng `epistex_assign`, Supervisor 15, lấy
từ `setup/kiro-<role>.json`), và chỉ trong bản sao `cli-config.json` riêng của seat. `cli-config.json` của
người dùng không đổi. Peer không nhận token nào. Tool khác vẫn theo quyền của Cursor.

## Chọn model và mức suy luận

Trên CLI `2026.10.18-ea085cb`, danh sách CLI có `grok-4.7-low` và `grok-4.7-medium`,
nhưng ACP mặc định từ chối hai ID này. Danh mục ACP chỉ công bố biến thể lấy từ tham số
đã lưu. Cấu hình `high, fast=true` có thể vì vậy còn hiệu lực khi client không xử lý lỗi chọn model.
Thêm `--model` trước `acp` không sửa được trường hợp đã kiểm tra.

Launcher khai báo `clientCapabilities._meta.parameterizedModelPicker=true`. Sau `session/new`
hoặc `session/load`, launcher dùng `session/set_config_option` để đặt các tham số của model default
của role theo bảng trên (ví dụ Peer: `model=composer-2.5`, `fast=false`). Khi Paseo chọn profile khác,
launcher đặt tham số của model đó bằng cùng giao thức.
Launcher kiểm tra đủ các giá trị trong phản hồi Cursor trước khi nhận prompt. Nếu Cursor gửi
`current_model_update` hoặc `config_option_update` mâu thuẫn với lựa chọn đã xác nhận, launcher
hủy xác nhận đó và chặn prompt tiếp theo cho đến khi chọn lại model và xác nhận đủ các giá trị.
Session khôi phục bằng `session/resume` không được launcher theo dõi, nên prompt của session đó bị từ chối; hãy dùng `session/load` hoặc tạo phiên mới.
Nếu chọn model thất bại hoặc Cursor trả giá trị khác, launcher chặn prompt. Không fallback sang Auto,
model khác, effort khác hoặc Fast. Không thêm `thinkingOptionId` vào profile.

Cursor ghi các tham số ACP vào `cli-config.json`. Launcher dùng bản sao riêng qua
`CURSOR_CONFIG_DIR` trong thư mục tạm có quyền riêng tư. Các tệp khác được liên kết về thư mục
Cursor gốc để giữ auth, MCP, rules và lịch sử phiên. `acp-config.json` cũng được tách riêng.
Không thay cấu hình model toàn cục. Thư mục tạm bị xóa khi launcher kết thúc; lịch sử phiên gốc được giữ.
Không dùng `--force`, `--yolo` hoặc `--approve-mcps` để vượt lỗi quyền.

## Kiểm tra sau cập nhật

Sau `paseo reload`, tạo phiên mới cho mỗi profile. Kiểm tra model, mức suy luận, Fast off,
vai trò Peer, CWD và công cụ thực tế. `paseoTools.enabled=false` không tắt MCP riêng của Cursor.
Nếu Cursor báo giới hạn gói hoặc quota, báo BLOCKED; không đổi model hoặc nâng cấp gói.

## Tự động thu gọn ngữ cảnh

CLI chưa có tùy chọn ngưỡng token được xác minh trong tài liệu cấu hình, help hoặc ACP config options
(kiểm lại trên `2026.11.13-eacade1`: ACP chỉ có `mode`, `model`, `reasoning_effort`, `context`, `fast`).
Giữ cơ chế mặc định của backend; không thêm khóa phỏng đoán. Ngưỡng 200.000 token của các seat khác
không áp dụng được cho Cursor. `/summarize` (alias `/compress`) là lệnh thủ công.

Nguồn: [ACP](https://cursor.com/docs/cli/acp),
[cấu hình CLI](https://cursor.com/docs/cli/reference/configuration),
[khả năng CLI](https://cursor.com/docs/cli/using),
[Grok 4.7](https://cursor.com/docs/models/grok-4-7).
Capability chọn tham số và các giá trị phản hồi đã được kiểm tra trực tiếp trên phiên bản nêu trên.

Live E2E (CLI `2026.10.22-27dcf5f`): `cursor-peer` `grok-4.7-low` launch qua
Paseo, nhận `# Common contract` cộng `# Peer — independent co-worker`, CWD là project, không thấy tool
Paseo. Catalog native có `Task` (subagent của Cursor) và MCP `semble`; đây không phải Paseo MCP.

Live (2026-11-14, CLI `2026.11.13-eacade1`, Paseo 0.15.4): `cursor-peer` `composer-2.5` nhận heading Peer,
CWD đúng, không có tool Paseo. `cursor-supervisor` `grok-4.7-high-500k` thấy đúng 15 tool Paseo;
`cursor-lead` `gemini-4-carbon-high` thấy đúng 8 tool. Cả hai gọi `list_workspaces` và `list_profiles`
không có permission request. Trước khi launcher thêm token `Mcp(paseo:…)`, cả hai dừng ở permission request.
Catalog tham số của ba model lấy từ probe ACP không gửi prompt.
