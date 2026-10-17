# SETUP — Devin Peer qua ACP

Dùng các bước chung trong [SETUP.md](../../SETUP.md), gồm mục
[ACP proxy seats](../../SETUP.md#acp-proxy-seats). Kiểm executable, auth và discovery của `devin` trước.

Devin chỉ có seat Peer. Không cấu hình Devin Lead hay Devin Supervisor: `setup/devin-acp`
từ chối mọi role khác `peer`.

| Field | `devin-peer` |
|---|---|
| `command` | `["<KIT>/setup/role-agent","peer","devin"]` |
| `paseoTools.enabled` | `false` |
| `models` | chỉ `swe-2-high` |
| `thinkingOptions` | `[{"id":"high","label":"High","isDefault":true}]` |
| Profile pin | `devin-peer--swe-2-high--high` |

Không cấu hình model Fusion. `role-agent peer devin` chuyển sang `setup/devin-acp peer` bằng
`os.execv`; launcher chạy `devin acp`. ACP hiện trả mode `accept-edits` cho phiên smoke test;
lấy mode thực tế từ discovery.
