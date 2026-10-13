# SETUP — Kiro Peer qua ACP

`kiro-peer` dùng `role-agent peer kiro` và adapter local `setup/kiro-acp`; không sửa
Paseo package hoặc global Kiro settings. Cần Kiro CLI đã đăng nhập, Python 3.11+,
và kit ở đường dẫn tuyệt đối. Cơ chế này được kiểm với CLI **2.30.0, engine v2**.
Không suy engine từ ACP protocol version: cả v2/v3 đều dùng version 1.

## Cài runtime và provider

Giữ nguyên credentials, sessions, settings và các agent khác. Cài riêng file seat-owned
`setup/kiro-peer.json` thành `~/.kiro/agents/epistex_peer.json`; nếu tên đó đã thuộc cấu hình
khác, dừng và xin quyết định của Human, không overwrite. Không dùng symlink.

```bash
mkdir -p ~/.kiro/agents
cp -n <KIT>/setup/kiro-peer.json ~/.kiro/agents/epistex_peer.json
kiro-cli agent validate --path ~/.kiro/agents/epistex_peer.json
```

Merge **chỉ** `agents.providers.kiro-peer` và bốn `daemon.agentProfiles` có provider
`kiro-peer` từ [provider mẫu](../../examples/paseo-providers.json), thay `<KIT>` bằng
đường dẫn kit. Giữ nguyên các provider khác. `extends=acp`, `paseoTools.enabled=false`.
Không thêm MCP server vào new/load của Peer.

| Model | Effort | Profile |
|---|---|---|
| `claude-opus-5.5` | `low` | `kiro-peer--claude-opus-5-5--low` |
| `claude-opus-5.5` | `medium` | `kiro-peer--claude-opus-5-5--medium` |
| `claude-sonnet-5.5` | `low` | `kiro-peer--claude-sonnet-5-5--low` |
| `claude-sonnet-5.5` | `medium` | `kiro-peer--claude-sonnet-5-5--medium` |

Orchestrator copy `provider`, `model`, `thinkingOptionId` vào `create_agent`, dùng project
workspace. **Không gửi `modeId`**: seat cố định `epistex_peer`, mọi mode switch bị từ chối.
Sau merge, chạy `setup/setup-seats.sh`, checker theo [SETUP.md](../../SETUP.md), rồi
`paseo reload` và tạo phiên mới. Static checker không chứng minh live launch.

## Effort thật, không chỉ profile labels

V2 không có `session/set_config_option`. Adapter expose option `epistex_effort`, category
`thought_level` mà Paseo generic ACP client cần. Khi nhận selection, adapter gửi typed
`_kiro.dev/commands/execute` với `command={"command":"effort","args":{"level":"low"}}`
(hoặc `medium`), yêu cầu `success=true`, rồi query `_kiro.dev/commands/options` cho **model
và effort** để xác nhận option `[active]` từ backend. Model setter trả success nhưng không
đổi model vẫn bị reject; confirmation nằm trong production adapter, không chỉ smoke test.
Response configOptions chỉ được trả sau confirmation; backend
error giữ nguyên code/message/data. Selection không hỗ trợ, effort không đổi, thiếu capability/
tool advertisement, backend exit hoặc hết hạn confirmation đều không báo thành công.

Đổi model có thể reset effort ở Kiro. Adapter reapply và confirm effort trước đó trước khi
trả model response: Paseo có thể bỏ qua setter nếu thinkingOptionId không thay đổi. Không
launch bằng `--model` hoặc `--effort`: các flag đó override model/effort khi load session.
Default model của session mới nằm trong seat config; effort được đọc từ backend, không giả
default `low`. Profile selection mới được Paseo áp dụng; load giữ model/effort đã lưu.

Engine v3 đã có standard config options `model`/`effortLevel` nhưng là API và permission
surface khác. Adapter này pin `--agent-engine=v2`, không tự fallback hoặc gọi lẫn extension
v2/v3. Khi nâng cấp, chạy probe và đọc initialize capabilities/returned options lại. `/effort`
v2 đang được backend đánh dấu deprecated; mất endpoint/confirmation phải fail, không no-op.

## Native topology và role

Seat dùng allowlist native tools; **không có `subagent`, `goal` hoặc Paseo MCP**. New/load
chỉ thành công sau khi mode/model và raw tool inventory đã được kiểm. Load bỏ inventory/session
validation cũ, đợi advertisement mới và kiểm lại inventory ngay trước response thành công;
inventory unsafe xuất hiện trong lúc confirmation làm load thất bại. Runtime installed phải
match byte-for-byte file kit. Workspace `.kiro/agents/epistex_peer.json`/`.md` (kể cả ancestor)
làm launch/session thất bại để tránh workspace override global agent. Không tự sửa override.
Mode switches, native agent/chat/rewind commands, subagent lifecycle và global setting writes
bị reject. Native `mcp`/`tools` chỉ được inspection với `args={}` đã probe trên backend;
mọi argument-bearing operation (add/remove, trust-all/trust/untrust/reset) bị reject trước
backend để giữ nguyên MCP/config/permission policy. Approval vẫn đi qua ACP permission request,
không qua native trust command. Notifications và unknown metadata giữ nguyên; unsupported agent-to-client requests
nhận JSON-RPC error, permission và negotiated fs/terminal callbacks relay bình thường.

Role instructions được prepend vào **prompt đầu tiên mỗi session trong vòng đời adapter**,
kể cả phiên load; không phải system prompt. `session/prompt`, cancellation, errors và replay
không được giả thành completion. Shell và cùng Unix user vẫn không phải OS sandbox; policy
không ngăn một agent độc hại sửa file config hoặc tự gọi CLI.

## Kiểm độc lập

Không gửi model prompt trong metadata probe:

```bash
EPISTEX_REAL_KIRO_PROBE=1 PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -p test_kiro_acp.py -v
```

Probe in raw backend metadata/tools và query active model/effort cho cả bốn selection; sau
đó load trong cùng process và process mới, kiểm Sonnet/medium còn nguyên và inspection không
thay permission policy. Fixture tests kiểm role/CWD, model reset và ignored model-set success,
cancellation, permission relay, unsafe inventory trong lúc load confirmation, native MCP/trust
mutations, unsafe modes/override, ignored effort, backend rejection và early exit. Không thay
live model smoke tests.

Lead launch bốn profile qua Paseo sau frozen-candidate review; lấy actual session/model/effort,
raw `_kiro.dev/metadata` và `_kiro.dev/commands/available` hoặc chạy metadata probe trên chính
candidate. Trong live task prompt, yêu cầu agent mô tả heading role **đã nhận trong session**,
liệt kê tools thực sự thấy và in `pwd`; không coi đọc lại file prompt là proof injection.
Peer phải nhận `# Peer — independent co-worker`, project CWD, không Paseo/subagent tools.
Lead kiểm thêm cancel/resume qua lifecycle Paseo. Chưa kiểm qua Paseo thì chỉ kết luận
ACP metadata/fixture verified, không kết luận seat đã được chấp nhận.

Nguồn authoritative (running capabilities thắng ví dụ tài liệu):
[ACP](https://kiro.dev/docs/acp/), [V2 ACP](https://kiro.dev/docs/cli/acp/),
[V3 migration](https://kiro.dev/docs/cli/v3/acp-migration/),
[custom agents](https://kiro.dev/docs/custom-agents/).
