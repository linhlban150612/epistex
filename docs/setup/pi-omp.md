# SETUP — Pi Peer và các seat OMP

Dùng các bước backup, merge, protocol, reload và live verification trong
[SETUP.md](../../SETUP.md). Kiểm executable `pi`, `omp`,
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
| `models[0].id` | `huggingface/deepseek-ai/DeepSeek-V4.1-Flash-1017` | `huggingface/deepseek-ai/DeepSeek-V4.1-Flash-1017` |
| `models[0].isDefault` | `true` | `true` |
| `models[0].thinkingOptions` | `[{"id":"low","label":"Low","isDefault":true}]` | same as `pi-peer` |

Effort mặc định của cả hai seat là `low` để giảm chi phí (`medium`/`high` vẫn chọn tay được qua profile);
`setup-seats.sh --check` kiểm default này. Kiểm lại discovery trước lần cài khác. Thay `<KIT>` bằng đường dẫn tuyệt đối, giữ launcher
executable, chạy `paseo reload` và tạo phiên mới với model/effort và mode từ discovery.
Khi chạy bằng CLI, truyền `--thinking low` để dùng đúng effort của profile.
Kiểm tra thực tế cho thấy lệnh không truyền effort có thể chạy ở `high`, dù profile đặt `low`.
Pi dùng `--append-system-prompt` native dạng lặp lại. OMP dùng một giá trị cuối cùng, nên
launcher gộp mọi giá trị `--append-system-prompt` của caller (gồm text hoặc file mà OMP đọc được)
với nội dung role trước khi gọi OMP. Các RPC args khác và stdin được giữ nguyên. Launcher giữ
CWD và auth home hiện có; không dùng ACP proxy cho hai backend này.

Kiểm phiên thực tế: heading từ active instructions phải là `# Peer — independent co-worker`,
`pwd` đúng workspace, model/effort đúng và không có Paseo tools trong inventory kể cả deferred
discovery nếu có. Không đọc file role để thay bằng chứng injection. Diagnostic không thay thế
live launch.

Mọi profile `omp-peer` có `modeId: full` (Full Access; Write Approval và Always Ask dừng Peer non-interactive ở permission request);
`--check` bắt buộc. `pi-peer` không có mode.

Mỗi seat có 12 profile. Profile model pins (profile effort options are `low` except where indicated):

| Seat | Model IDs | Effort pins |
|---|---|---|
| `pi-peer` | `huggingface/deepseek-ai/DeepSeek-V4.1-Flash-1017`; `openrouter/deepseek/deepseek-v4.1-flash-1017`; `openai-codex/gpt-6-luna`; `openrouter/moonshotai/kimi-k3`; `openrouter/z-ai/glm-5.3-flash`; `openrouter/z-ai/glm-5.3`; `openrouter/anthropic/claude-haiku-5.5`; `xai/grok-4.7` | low; GPT-6 Luna, Haiku and Grok 4.7 also medium; GLM-5.3 also high |
| `omp-peer` | Same list as `pi-peer`, but Grok 4.7 is `xai-oauth/grok-4.7` | low; GPT-6 Luna, Haiku and Grok 4.7 also medium; GLM-5.3 also high |

Chỉ dùng `pi-peer`/`omp-peer` để điều phối khi Human cho phép delegation. Không xóa session
hay thay credentials; role/MCP separation không phải OS sandbox.

Do not use `github-copilot/gpt-6-luna` (Copilot quota 429). Grok 4.7 uses xAI OAuth (`xai` in Pi, `xai-oauth` in OMP), not OpenRouter. OMP compaction still uses the fixed `thresholdTokens` in `.omp/config.yml`.

## Seat OMP trên model Factory

`omp-supervisor`, `omp-lead`, `omp-peer-1`, `omp-peer-2` và `omp-peer-3` dùng provider `factory-droid` của OMP,
với cùng model và effort như các seat Droid ([droid.md](droid.md)). `omp-peer` ở trên giữ nguyên.

| Seat | `command` | Paseo tools | Model (`factory-droid/<id>`) | Default |
|---|---|---|---|---|
| `omp-supervisor` | `["<KIT>/setup/role-agent","supervisor","omp"]` | 15 tool Supervisor | `claude-opus-5-5`, `claude-sonnet-5-5`, `gpt-6.1-sol`, `gemini-4-argon`; low/medium | `claude-sonnet-5-5`, low |
| `omp-lead` | `["<KIT>/setup/role-agent","lead","omp"]` | 8 tool Lead | như `omp-supervisor` | `claude-opus-5-5`, low |
| `omp-peer-1`…`3` | `["<KIT>/setup/role-agent","peer","omp"]` | tắt | chín model của `droid-peer`, cùng effort | `claude-haiku-5-5`, low |

Mọi seat có `extends: "omp"`; mọi profile có `modeId: full`. Deny-list của Lead và Supervisor theo
[SETUP.md §3](../../SETUP.md#paseo-tools-policy-for-lead-and-supervisor). Paseo nối MCP vào OMP bằng bridge
riêng, nên tool Paseo xuất hiện như tool thường của OMP. `setup-seats.sh --check` kiểm launcher, tool,
env, model/effort và đủ profile cho mỗi seat đang bật.

**Login riêng cho mỗi seat.** Provider `factory-droid` của OMP dùng login lưu trong profile OMP, không
đọc API key từ env. `env` của seat là `{}` (login mặc định trong `~/.omp/agent`, dùng chung) hoặc đúng một
`OMP_PROFILE` (tên profile, duy nhất cho mỗi seat). Để tách login: chạy `omp --profile <tên>`, đăng nhập
Factory bằng `/login`, rồi đặt `"env": {"OMP_PROFILE": "<tên>"}` cho seat, `paseo reload` và launch thử.
Chưa kiểm live một seat chạy với `OMP_PROFILE`; kiểm lịch sử phiên và model discovery sau khi đặt.
Trong config thật, `omp-peer-2` và `omp-peer-3` tắt và không có profile cho đến khi có login riêng.

Trạng thái live (2026-11-14, OMP 18.20.0, Paseo 0.15.4, login mặc định): `omp-supervisor` Sonnet/low thấy
đúng 15 tool Paseo, `omp-lead` Opus/low thấy đúng 8 tool; cả hai gọi `list_workspaces` không bị hỏi quyền
và nhận heading role đúng. `omp-peer-1` Haiku/low nhận `# Peer — independent co-worker`, CWD đúng, không có
tool Paseo. Tool native `task` của OMP vẫn có ở mọi seat OMP; đó không phải Paseo MCP và prompt role cấm
dùng nó để delegate.
