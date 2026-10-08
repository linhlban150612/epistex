# SETUP — Hai seat Claude riêng

Giữ nguyên contract/protocol và các bước backup, merge, MCP injection, reload, live verification
trong [SETUP.md](../../SETUP.md). Không dùng `codex-room` cho Claude.
Kiểm `claude --version`, `claude auth status` và `paseo provider models claude --json` trước.
Merge hai provider vào `.agents.providers`, với cấu hình:

| Field | `claude-lead` | `claude-peer` |
|---|---|---|
| `extends` | `claude` | `claude` |
| `command` | `["<KIT>/setup/role-agent", "lead", "claude"]` | `["<KIT>/setup/role-agent", "peer", "claude"]` |
| `enabled` | `true` | `true` |
| `env` | `{}` | `{}` |
| `paseoTools.enabled` | `true` | `false` |
| `models[0].id` | `claude-opus-5-5` | `claude-sonnet-5-5` |
| `models[0].isDefault` | `true` | `true` |
| `models[0].thinkingOptions` | `[{"id":"low","label":"Low","isDefault":true}]` | `[{"id":"low","label":"Low","isDefault":true}]` |

Profile pins:

| Seat | Model | Thinking options |
|---|---|---|
| `claude-peer` | `claude-opus-5-5` | `low`, `medium` |
| `claude-supervisor` | `claude-fable-5-1` | `medium` (unverified: provider credits) |

Claude Lead dùng deny-list tại [SETUP.md §3](../../SETUP.md); không áp dụng cho Peer.

Đặt label/description theo role và thay `<KIT>` bằng đường dẫn tuyệt đối. `role-agent` phải
executable. Launcher giữ CWD của Paseo và dùng Claude home/auth hiện có; không sinh hai
Codex runtime hay thay canonical Claude settings. Trong Claude SDK stream-json, launcher
thêm prompt role vào `request.appendSystemPrompt` của bản tin `control_request` / `initialize`,
giữ nguyên system prompt, append text và các field khác của SDK. Flag CLI
`--append-system-prompt` đơn lẻ không đủ vì SDK initialize thay cấu hình prompt đó.

Sau `paseo reload`, tạo phiên mới với model, `thinking=low` và mode lấy từ discovery.
Yêu cầu agent in heading role **từ system instructions đang hoạt động**, không đọc file prompt
để thay bằng chứng. Lead phải có heading `# Lead — Project Lead & binding technical arbiter`,
thấy Paseo tools và gọi được một tool read-only; Peer phải có heading
`# Peer — independent co-worker` và không thấy Paseo tools kể cả qua deferred tool discovery.
Lead điều phối Peer Claude bằng `claude-peer`, không dùng provider Claude gốc.

`setup-seats.sh --check` kiểm các supervisor seat. Claude Peer profiles pin `claude-opus-5-5` ở low/medium; Supervisor profile pin `claude-fable-5-1` ở medium (unverified: provider credits). Kiểm field provider và chạy launch thật cho các role.
Đây là role/MCP separation, không phải OS sandbox hay hai credential home cô lập.
