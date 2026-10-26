# SETUP — Cursor Peer qua ACP

Dùng các bước chung trong [SETUP.md](../../SETUP.md), gồm mục
[ACP proxy seats](../../SETUP.md#acp-proxy-seats). Kiểm executable, auth và discovery của `cursor-agent` trước.

| Field | `cursor-peer` |
|---|---|
| `command` | `["<KIT>/setup/role-agent","peer","cursor"]` |
| `paseoTools.enabled` | `false` |
| `models` | `grok-4.7-low` (default); `grok-4.7-medium` |
| `thinkingOptions` | Không có; launcher chuyển model ID thành tham số ACP |
| Fast / context | `fast=false`; `context=256k` cho cả hai profile |
| Profile pin | `cursor-peer--grok-4-7-low`; `cursor-peer--grok-4-7-medium` |

`role-agent <role> cursor` chuyển sang `setup/cursor-acp <role>` bằng `os.execv`; launcher chạy
`cursor-agent acp`. Hai ID trên là ID của seat, không phải ID gửi trực tiếp cho Cursor ACP.

## Chọn model và mức suy luận

Trên CLI `2026.10.18-ea085cb`, danh sách CLI có `grok-4.7-low` và `grok-4.7-medium`,
nhưng ACP mặc định từ chối hai ID này. Danh mục ACP chỉ công bố biến thể lấy từ tham số
đã lưu. Cấu hình `high, fast=true` có thể vì vậy còn hiệu lực khi client không xử lý lỗi chọn model.
Thêm `--model` trước `acp` không sửa được trường hợp đã kiểm tra.

Launcher khai báo `clientCapabilities._meta.parameterizedModelPicker=true`. Sau `session/new`
hoặc `session/load`, launcher dùng `session/set_config_option` để chọn `model=grok-4.7`,
`fast=false`, `context=256k` và `reasoning_effort=low`. Khi Paseo chọn profile medium,
launcher đặt `reasoning_effort=medium` bằng cùng giao thức.
Launcher kiểm tra đủ bốn giá trị trong phản hồi Cursor trước khi nhận prompt. Nếu Cursor gửi
`current_model_update` hoặc `config_option_update` mâu thuẫn với lựa chọn đã xác nhận, launcher
hủy xác nhận đó và chặn prompt tiếp theo cho đến khi chọn lại model và xác nhận đủ bốn giá trị.
Nếu chọn model thất bại hoặc Cursor trả giá trị khác, launcher chặn prompt. Không fallback sang Auto,
Composer, high hoặc Fast. Giữ nguyên hai profile low/medium; không thêm `thinkingOptionId`.

Cursor ghi các tham số ACP vào `cli-config.json`. Launcher dùng bản sao riêng qua
`CURSOR_CONFIG_DIR` trong thư mục tạm có quyền riêng tư. Các tệp khác được liên kết về thư mục
Cursor gốc để giữ auth, MCP, rules và lịch sử phiên. `acp-config.json` cũng được tách riêng.
Không thay cấu hình model toàn cục. Thư mục tạm bị xóa khi launcher kết thúc; lịch sử phiên gốc được giữ.
Không dùng `--force`, `--yolo` hoặc `--approve-mcps` để vượt lỗi quyền.

## Kiểm tra sau cập nhật

Sau `paseo reload`, tạo phiên mới cho cả hai profile. Kiểm tra model, mức suy luận, Fast off,
vai trò Peer, CWD và công cụ thực tế. `paseoTools.enabled=false` không tắt MCP riêng của Cursor.
Nếu Cursor báo giới hạn gói hoặc quota, báo BLOCKED; không đổi model hoặc nâng cấp gói.

## Tự động thu gọn ngữ cảnh

CLI `2026.10.18-ea085cb` chưa có tùy chọn ngưỡng 100.000 token được xác minh trong tài liệu
cấu hình, help hoặc ACP config options. Giữ cơ chế mặc định của backend; không thêm khóa phỏng đoán.
`/summarize` (alias `/compress`) là lệnh thủ công, không phải cấu hình tự động ở 100k.

Nguồn: [ACP](https://cursor.com/docs/cli/acp),
[cấu hình CLI](https://cursor.com/docs/cli/reference/configuration),
[khả năng CLI](https://cursor.com/docs/cli/using),
[Grok 4.7](https://cursor.com/docs/models/grok-4-7).
Capability chọn tham số và các giá trị phản hồi đã được kiểm tra trực tiếp trên phiên bản nêu trên.

Live E2E (2026-10-25, CLI `2026.10.22-27dcf5f`, Paseo 0.13.0): `cursor-peer` `grok-4.7-low` launch qua
Paseo, nhận `# Common contract` cộng `# Peer — independent co-worker`, CWD là project, không thấy tool
Paseo. Catalog native có `Task` (subagent của Cursor) và MCP `semble`; đây không phải Paseo MCP.
