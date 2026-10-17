# SETUP — Kiro Lead và Peer qua ACP

`kiro-peer` dùng `role-agent peer kiro`, `kiro-lead` dùng `role-agent lead kiro`; cả hai
đi qua adapter local `setup/kiro-acp <role>`; không sửa
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

## Kiro Lead

`kiro-lead` cài riêng `setup/kiro-lead.json` thành `~/.kiro/agents/epistex_lead.json` (đúng
bytes, không symlink; tên đã thuộc cấu hình khác thì dừng hỏi Human), rồi merge **chỉ**
`agents.providers.kiro-lead` và bốn profile `kiro-lead--claude-{opus,sonnet}-5-5--{low,medium}`
từ [provider mẫu](../../examples/paseo-providers.json). Model/effort giống Peer (bảng trên);
`low`/`medium` là choices do backend trả qua `_kiro.dev/commands/options` và adapter confirm
`[active]` như Peer. Mode cố định `epistex_lead`.

```bash
cp -n <KIT>/setup/kiro-lead.json ~/.kiro/agents/epistex_lead.json
kiro-cli agent validate --path ~/.kiro/agents/epistex_lead.json
```

Provider: `extends=acp`, command `["<KIT>/setup/role-agent","lead","kiro"]`,
`paseoTools.enabled=true` với đúng 49 `disabledTools` của Lead policy trong
[SETUP.md](../../SETUP.md); Paseo enforce danh sách đó ở server. Agent file chỉ cho phép
native tools của Peer cộng đúng 12 tool Lead dạng `@paseo/<tool>`; `allowedTools=[]` nên mọi
tool call đi qua ACP `session/request_permission` mà Paseo relay — không auto-approve.
`includeMcpJson=false`, `mcpServers={}`: không đọc MCP từ workspace hoặc global config.

**MCP được chấp nhận** trên `session/new`, `session/load`, `session/resume`: `[]` hoặc đúng một
server `{"type":"http","name":"paseo","url":…,"headers":…}` với đúng bốn key đó;
URL `http://<host>:<port>/mcp/agents?callerAgentId=<id>` với host `127.0.0.1`, `localhost`
hoặc `::1`, có port, không userinfo/fragment, query chỉ một `callerAgentId` khác rỗng;
`headers` là `[]` hoặc đúng một `{"name":"Authorization","value":"Bearer <token>"}`.
`[]` chỉ dành cho session probe của Paseo (catalog/features/diagnostics — đã quan sát các probe
Paseo 0.11 gửi `mcpServers: []`); session probe không bao giờ được chạy `session/prompt`, còn
session thật cần đúng server Paseo trên. Mọi thứ khác bị reject trước backend: không có/nhiều
server, stdio/sse, tên khác, key thừa, https, host không loopback, path/query khác, header
khác. `session/resume` chạy cùng validator MCP và CWD như load cho cả hai role; session được
resume thay thế trạng thái cũ, huỷ confirmation đang chờ và không được track, nên prompt vẫn
bị refuse. Peer vẫn reject mọi MCP server.

Kiro v2 quảng bá tool runtime bằng tên bare (native lẫn MCP, vd `list_agents` chứ không
`@paseo/list_agents`); adapter so với native cộng tên bare của 12 entry `@paseo/<tool>` trong
agent file. Tool lạ (kể cả `speak`, tool Paseo bị chặn, server khác, literal `@paseo/x` hoặc
`subagent`) làm session thất bại thay vì expose. Giới hạn chưa chứng minh: metadata probe
(`kiro-cli acp` initialize) đòi đăng nhập nên `mcpCapabilities.http` của v2 chưa được quan
sát; Paseo có quảng bá `speak` cho Kiro hay không chỉ được xác định bằng live launch. Nếu
khác, seat fail closed; đổi allowlist cần Human quyết định.

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

Peer seat dùng allowlist native tools; **không có `subagent`, `goal` hoặc Paseo MCP** (Lead
giữ đúng một server Paseo injected như trên). New/load
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
Live E2E hiện chỉ phủ create/prompt/gọi MCP `list_workspaces`/archive; `session/cancel`,
`session/resume` và `session/load` qua lifecycle Paseo chưa được live-cover. Chưa kiểm qua Paseo thì chỉ kết luận
ACP metadata/fixture verified, không kết luận seat đã được chấp nhận.

Nguồn authoritative (running capabilities thắng ví dụ tài liệu):
[ACP](https://kiro.dev/docs/acp/), [V2 ACP](https://kiro.dev/docs/cli/acp/),
[V3 migration](https://kiro.dev/docs/cli/v3/acp-migration/),
[custom agents](https://kiro.dev/docs/custom-agents/).
A `kiro-supervisor` seat also exists: `role-agent supervisor kiro`, `setup/kiro-supervisor.json`, installed agent `~/.kiro/agents/epistex_supervisor.json`, Supervisor Paseo tool set (keeps `create_workspace`).
