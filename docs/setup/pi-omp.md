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
| `models[0].id` | `github-copilot/gpt-6-luna` | `openrouter/z-ai/glm-5.3` |
| `models[0].isDefault` | `true` | `true` |
| `models[0].thinkingOptions` | `[{"id":"medium","label":"Medium","isDefault":true}]` | `[{"id":"low","label":"Low","isDefault":false},{"id":"high","label":"High","isDefault":true}]` |

`medium`/`high` là effort mặc định discovery tại lần cài này khi Human không chỉ định effort;
kiểm lại discovery trước lần cài khác. Thay `<KIT>` bằng đường dẫn tuyệt đối, giữ launcher
executable, chạy `paseo reload` và tạo phiên mới với model/effort và mode từ discovery.
Launcher dùng native `--append-system-prompt <KIT>/agents/PEER.md`, chuyển tiếp RPC args
và stdin nguyên trạng, giữ CWD và auth home hiện có; không dùng ACP proxy cho hai backend này.

Kiểm phiên thực tế: heading từ active instructions phải là `# Peer — independent co-worker`,
`pwd` đúng workspace, model/effort đúng và không có Paseo tools trong inventory kể cả deferred
discovery nếu có. Không đọc file role để thay bằng chứng injection. Diagnostic không thay thế
live launch. `setup-seats.sh --check` kiểm Codex và Supervisor; kiểm riêng các provider này. Pi Peer có chín profile (DeepSeek Flash low, GPT-6 Luna low/medium, Kimi K3 low, GLM-5.3 Flash low, GLM-5.3 low/high, Claude Haiku 5.5 low/medium). OMP Peer có chín profile tương tự, gồm GPT-6 Luna low/medium; GLM-5.3 giữ high mặc định ở model seat.
Profile model pins (profile effort options are `low` except where indicated):

| Seat | Model IDs | Effort pins |
|---|---|---|
| `pi-peer` | `openrouter/deepseek/deepseek-v4.1-flash`; `github-copilot/gpt-6-luna`; `openrouter/moonshotai/kimi-k3`; `openrouter/z-ai/glm-5.3-flash`; `openrouter/z-ai/glm-5.3`; `openrouter/anthropic/claude-haiku-5.5` | low; GPT-6 Luna and Haiku also medium; GLM-5.3 also high |
| `omp-peer` | Same list as `pi-peer` | low; GPT-6 Luna and Haiku also medium; GLM-5.3 also high, model default remains high |

Chỉ dùng `pi-peer`/`omp-peer` để điều phối khi Human cho phép delegation. Không xóa session
hay thay credentials; role/MCP separation không phải OS sandbox.

OMP 18.8.4 hỗ trợ `github-copilot/gpt-6-luna` với effort low/medium. Cell GPT-6 Luna
của `omp-peer` có label `GPT-6 Luna`, `isDefault: false`, low mặc định và medium
tùy chọn; cell `pi-peer` cùng label là default của seat với medium mặc định. Compaction OMP vẫn dùng `thresholdTokens` cố định trong `.omp/config.yml`.

Known issue: OMP 18.8.4 resolves github-copilot/gpt-6-luna to gpt-5.6-luna (272k) — observed in probe 2026-10-08; re-verify after OMP updates
