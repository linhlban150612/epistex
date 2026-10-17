# SETUP — Pi Peer và OMP Peer riêng

Dùng các bước backup, merge, protocol, reload và live verification trong
[SETUP.md](../../SETUP.md). Không cần cài 21 standalone profile. Kiểm executable `pi`, `omp`,
auth của backend và discovery bằng `paseo provider models pi --json`,
`paseo provider models omp --json` trước khi cấu hình.
Không in credential để kiểm auth.

Merge vào `.agents.providers`, giữ nguyên provider và state hiện có:

| Field | `pi-peer` | `omp-peer` |
|---|---|---|
| `extends` | `pi` | `omp` |
| `command` | `["<KIT>/setup/role-agent", "peer", "pi"]` | `["<KIT>/setup/role-agent", "peer", "omp"]` |
| `enabled` | `true` | `true` |
| `env` | `{}` | `{}` |
| `paseoTools.enabled` | `false` | `false` |
| `models[0].id` | `openai-codex/gpt-6-luna` | `openai-codex/gpt-6-luna` |
| `models[0].isDefault` | `true` | `true` |
| `models[0].thinkingOptions` | `[{"id":"low","label":"Low","isDefault":true},{"id":"medium","label":"Medium","isDefault":false}]` | same as `pi-peer` |

Effort mặc định của cả hai seat là `low` để giảm chi phí (`medium`/`high` vẫn chọn tay được qua profile);
`setup-seats.sh --check` kiểm default này. Kiểm lại discovery trước lần cài khác. Thay `<KIT>` bằng đường dẫn tuyệt đối, giữ launcher
executable, chạy `paseo reload` và tạo phiên mới với model/effort và mode từ discovery.
Launcher dùng native `--append-system-prompt <KIT>/agents/PEER.md`, chuyển tiếp RPC args
và stdin nguyên trạng, giữ CWD và auth home hiện có; không dùng ACP proxy cho hai backend này.

Kiểm phiên thực tế: heading từ active instructions phải là `# Peer — independent co-worker`,
`pwd` đúng workspace, model/effort đúng và không có Paseo tools trong inventory kể cả deferred
discovery nếu có. Không đọc file role để thay bằng chứng injection. Diagnostic không thay thế
live launch. `setup-seats.sh --check` kiểm Codex và Supervisor; kiểm riêng các provider này. Pi Peer có chín profile (DeepSeek Flash low, GPT-6 Luna low/medium, Kimi K3 low, GLM-5.3 Flash low, GLM-5.3 low/high, Claude Haiku 5.5 low/medium). OMP Peer có chín profile tương tự, gồm GPT-6 Luna low/medium; GPT-6 Luna (`openai-codex`) là default của cả hai seat, effort mặc định low.
Profile model pins (profile effort options are `low` except where indicated):

| Seat | Model IDs | Effort pins |
|---|---|---|
| `pi-peer` | `openrouter/deepseek/deepseek-v4.1-flash`; `openai-codex/gpt-6-luna`; `openrouter/moonshotai/kimi-k3`; `openrouter/z-ai/glm-5.3-flash`; `openrouter/z-ai/glm-5.3`; `openrouter/anthropic/claude-haiku-5.5` | low; GPT-6 Luna and Haiku also medium; GLM-5.3 also high |
| `omp-peer` | Same list as `pi-peer` | low; GPT-6 Luna and Haiku also medium; GLM-5.3 also high |

Chỉ dùng `pi-peer`/`omp-peer` để điều phối khi Human cho phép delegation. Không xóa session
hay thay credentials; role/MCP separation không phải OS sandbox.

Both seats default to `openai-codex/gpt-6-luna` (low default, medium optional). Do not use `github-copilot/gpt-6-luna` (Copilot quota 429). OMP compaction still uses the fixed `thresholdTokens` in `.omp/config.yml`.
