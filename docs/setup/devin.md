# SETUP — Devin Peer và Supervisor qua ACP

Dùng các bước chung trong [SETUP.md](../../SETUP.md), gồm mục
[ACP proxy seats](../../SETUP.md#acp-proxy-seats). Kiểm executable, auth và discovery của `devin` trước.

Devin có seat Peer và seat Supervisor. Không cấu hình Devin Lead: `setup/devin-acp` từ chối role `lead`.

| Field | `devin-peer` | `devin-supervisor` |
|---|---|---|
| `command` | `["<KIT>/setup/role-agent","peer","devin"]` | `["<KIT>/setup/role-agent","supervisor","devin"]` |
| `paseoTools` | `enabled: false` | 15 tool Supervisor ([SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor)) |
| `models` | chỉ `swe-2-high` | chỉ `swe-2-high` |
| `thinkingOptions` | `medium` (default), `high` | `medium` (default), `high` |
| Profile pin | `devin-peer--swe-2-high--medium`, `--high` | `devin-supervisor--swe-2-high--medium`, `--high` |
| `modeId` | `bypass` | `bypass` |

Không cấu hình model Fusion. `swe-2-high` là model ID duy nhất mà Devin ACP nhận cho SWE-2; nó không
phải mức effort. Effort là option ACP `thought_level` (`medium`, `high`, `max`), và Paseo đặt nó từ
`thinkingOptionId`. Kiểm live: profile medium báo "SWE-2 Medium", profile high báo "SWE-2 High".

**Fast mode tắt.** Devin ACP có option `speed` (`standard`, `fast`). `setup/devin-acp` đặt `speed=standard`
cho mỗi phiên new/load/resume trước khi client biết phiên đó, từ chối yêu cầu đặt giá trị khác, và từ chối
prompt khi backend chưa xác nhận `standard` (kể cả khi backend tự đổi sang `fast` giữa phiên).

**Mode.** Devin ACP có `accept-edits`, `smart`, `ask`, `plan`, `bypass`. Paseo không kế thừa mode của Lead
sang provider khác, nên mọi profile có `modeId: bypass`; `--check` bắt buộc. Các mode khác có thể dừng một
seat không người trực ở permission request.

`role-agent <role> devin` chuyển sang `setup/devin-acp <role>` bằng `os.execv`; launcher chạy `devin acp`.

Trạng thái live (2026-11-14, Devin 3000.12.57, Paseo 0.15.4): `devin-peer` medium nhận `# Common contract`
cộng `# Peer — independent co-worker`, CWD đúng, không có tool Paseo. `devin-supervisor` high nhận
`# Supervisor — Paseo-only observer`, thấy đúng 15 tool Paseo và gọi `list_workspaces` không bị hỏi quyền.
Probe ACP qua launcher (không gửi prompt): `speed` là `standard`, yêu cầu `speed=fast` bị từ chối.
MCP riêng của Devin (ví dụ `figma`, `semble`) vẫn có; đó không phải Paseo MCP.
