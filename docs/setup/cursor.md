# SETUP — Cursor Peer qua ACP

Dùng các bước chung trong [SETUP.md](../../SETUP.md), gồm mục
[ACP proxy seats](../../SETUP.md#acp-proxy-seats). Kiểm executable, auth và discovery của `cursor-agent` trước.

| Field | `cursor-peer` |
|---|---|
| `command` | `["<KIT>/setup/role-agent","peer","cursor"]` |
| `paseoTools.enabled` | `false` |
| `models` | `composer-2.5[fast=true]` |
| `thinkingOptions` | Không có |
| Profile pin | `cursor-peer--composer-2-5-fast` |

`role-agent <role> cursor` chuyển sang `setup/cursor-acp <role>` bằng `os.execv`; launcher chạy
`cursor-agent acp`. Không thêm thinking option cho Composer 2.5. Cursor summary trả ID trần
`composer-2.5`, nhưng ACP session catalog/set-model yêu cầu `composer-2.5[fast=true]`; ID trần
bị từ chối và phiên đầu vẫn ở `default[]`. Kiểm lại catalog của phiên và metadata sau launch,
không chỉ discovery summary. ACP hiện trả mode `agent` cho phiên smoke test.

Nếu Cursor trả `Upgrade your plan to continue` sau khi metadata đã chọn đúng Composer,
đó chưa phải phiên smoke test thành công. Giữ model yêu cầu, báo giới hạn tài khoản và kiểm
lại sau khi Human xử lý quyền sử dụng; không tự chuyển Auto hay nâng cấp gói để vượt lỗi.
