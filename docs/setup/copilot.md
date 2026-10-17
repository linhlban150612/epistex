# SETUP — GitHub Copilot Peer qua ACP

Dùng các bước chung trong [SETUP.md](../../SETUP.md), gồm mục
[ACP proxy seats](../../SETUP.md#acp-proxy-seats). Kiểm executable, auth và discovery của `copilot` trước.

Copilot chỉ có seat Peer: `setup/copilot-acp` từ chối mọi role khác `peer`.

| Field | `copilot-peer` |
|---|---|
| `command` | `["<KIT>/setup/role-agent","peer","copilot"]` |
| `paseoTools.enabled` | `false` |
| `models` | `gemini-3.8-flash`, `kimi-k3`, `claude-haiku-5.5`, `grok-4.7`, `claude-sonnet-5.5` |
| `thinkingOptions` | `low`, `medium` cho từng model |

Profile pins: mỗi model ở `low` và `medium` (10 profile `copilot-peer--<model-slug>--<thinking>`).

`role-agent peer copilot` chuyển sang `setup/copilot-acp peer` bằng `os.execv`; launcher chạy
`copilot --acp`. ACP hiện trả mode `https://agentclientprotocol.com/protocol/session-modes#agent`
cho phiên smoke test; không suy ra mode ID `default` từ nhãn/default summary.
