# SETUP — Kiro Lead và Peer qua ACP

`kiro-peer` dùng `role-agent peer kiro`, `kiro-lead` dùng `role-agent lead kiro`; cả hai
đi qua adapter local `setup/kiro-acp <role>`; không sửa
Paseo package hoặc global Kiro settings. Cần Kiro CLI đã đăng nhập, Python 3.11+,
và kit ở đường dẫn tuyệt đối. Cơ chế này được kiểm với CLI **2.33.1, engine V3**
(`kiro-cli acp --agent-engine=v3 --auth-method=cli`, KAS 0.66.58); engine v2 không còn được hỗ trợ.
Không suy engine từ ACP protocol version: cả v2/v3 đều dùng version 1.

## Cài runtime và provider

Giữ nguyên credentials, sessions, settings và các agent khác. Cài riêng file seat-owned
`setup/kiro-peer.json` thành `~/.kiro/agents/epistex_peer.json`; nếu tên đó đã thuộc cấu hình
khác, dừng và xin quyết định của Human, không overwrite. Không dùng symlink.
Nâng cấp từ seat v2: file cài cũ có `allowedTools` và V3 **bỏ qua** profile có `allowedTools`
mà không có `permissions`. Nếu file đang cài trùng byte với bản v2 của kit thì backup
(`.before-v3-<timestamp>`) rồi copy bản mới; `cp -n` không ghi đè.

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

Default model của `kiro-peer` và `kiro-supervisor` là `claude-sonnet-5.5` (effort `low`) để giảm chi phí; `setup/kiro-peer.json` và
`setup/kiro-supervisor.json` đặt `model` là `claude-sonnet-5.5`, `setup/kiro-lead.json` đặt `claude-opus-5.5`: adapter yêu cầu model ban đầu của session nằm trong `MODELS`, nên bỏ trường này làm launch lỗi "Kiro restored an unsupported mode/model". Paseo vẫn đổi model qua profile: V3 không có `session/set_model`, adapter trả `-32601` để Paseo dùng `session/set_config_option` `configId=model`. `kiro-lead` giữ default `claude-opus-5.5` ở seat config. Opus vẫn chọn tay qua profile.

Orchestrator copy `provider`, `model`, `thinkingOptionId` vào `create_agent`, dùng project
workspace. **Không gửi `modeId`**: seat cố định `epistex_peer`, mọi mode switch bị từ chối.
Sau merge, chạy `setup/setup-seats.sh`, checker theo [SETUP.md](../../SETUP.md), rồi
`paseo reload` và tạo phiên mới. Static checker không chứng minh live launch.

## Kiro Lead

`kiro-lead` cài riêng `setup/kiro-lead.json` thành `~/.kiro/agents/epistex_lead.json` (đúng
bytes, không symlink; tên đã thuộc cấu hình khác thì dừng hỏi Human), rồi merge **chỉ**
`agents.providers.kiro-lead` và bốn profile `kiro-lead--claude-{opus,sonnet}-5-5--{low,medium}`
từ [provider mẫu](../../examples/paseo-providers.json). Model/effort giống Peer (bảng trên);
`low`/`medium` là choices trong option `effortLevel` do backend trả và adapter confirm
`currentValue` như Peer. Mode cố định `epistex_lead`.

```bash
cp -n <KIT>/setup/kiro-lead.json ~/.kiro/agents/epistex_lead.json
kiro-cli agent validate --path ~/.kiro/agents/epistex_lead.json
```

Provider: `extends=acp`, command `["<KIT>/setup/role-agent","lead","kiro"]`,
`paseoTools.enabled=true` với đúng 50 `disabledTools` của Lead policy trong
[SETUP.md](../../SETUP.md); Paseo enforce danh sách đó ở server. Agent file chỉ cho phép
tag native của Peer (`read`, `write`, `shell`, `web`) cộng đúng 11 tool Lead dạng
`@paseo/<tool>`. Không có `allowedTools`/`toolsSettings`: quyền nằm trong `permissions.rules` của agent
(allow `fs_read`, `fs_write`, `shell`, `web_fetch`, `web_search`; Lead thêm `mcp` match đúng 11
`paseo/<tool>`), nên Lead tự duyệt mọi tool (bypass) và Peer không bị hỏi quyền mỗi lần gọi. Policy
built-in của Kiro (vd chặn ghi settings của chính Kiro) và deny ở scope khác vẫn thắng; tool khác vẫn
hỏi qua ACP permission request. `use_aws`/`todo_list` của v2 không còn là built-in V3 nên đã bỏ.
`knowledge` cũng đã bỏ (2026-10-23, CLI 2.33.1): V3 hiện không cung cấp tool này (không quảng bá thành
tag) và nó vẫn là experimental. Chỉ enable lại khi V3 thực sự quảng bá `knowledge`; khi đó thêm lại vào
`tools` của cả ba file và kiểm capability/permission tương ứng, nếu không Lead có thể bị hỏi quyền.
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

Kiro V3 quảng bá tool qua `_kiro/tools/didChange` dạng **tag**: category builtin (`read`, `write`,
`shell`, `web`) và `@paseo/<tool>` cho MCP tool mà agent `tools` chọn (live: server trả thêm
`kill_agent`/`list_agents` vẫn bị Kiro lọc khỏi tag). Adapter yêu cầu tag ⊆ `tools` của agent file
và, với session có Paseo, đủ 11 tag `@paseo/<tool>`. `_kiro/mcp/status` là snapshot đầy đủ; Kiro báo
`connected` **trước** `didChange` mang tag MCP, nên adapter đợi một `didChange` mới hơn snapshot (tối đa
30 s) rồi mới kết luận. Tag lạ (kể cả `subagent`, bare `kill_agent`, `@paseo/<tool bị chặn>`, server
khác) hoặc thiếu tool Paseo làm session thất bại thay vì expose. V3 tải MCP tool theo yêu cầu: model
chỉ thấy `tool_load`/`tool_call`, và catalog của `tool_load` chỉ gồm tool được chọn trong `tools`.
`speak` (live 2026-10-23, Paseo 0.12.0): server chỉ đăng ký `speak` khi bật voice tools, và khi đó
`disabledTools` không chặn được nó; launch thường không có `speak` trong catalog Lead/Supervisor. Nếu
`@paseo/speak` xuất hiện thành tag, seat fail closed; đổi allowlist cần Human quyết định.

## Model/effort qua standard config options

V3 dùng `session/set_config_option` với `configId=model` và `configId=effortLevel` (category
`thought_level`); `session/set_model`, `_kiro.dev/commands/*` và `/effort` không còn. Adapter chỉ cho
qua hai option này, giá trị trong `MODELS`/`EFFORTS`; `mode`, `autopilot`, `memoryReflection`,
`contentCollection` và option lạ bị ẩn khỏi `configOptions` (response lẫn `config_option_update`) và
bị reject khi set. Live 2.33.1 trả success nhưng **giữ nguyên giá trị** khi value không hợp lệ, nên
adapter chỉ trả thành công khi `currentValue` trong response bằng giá trị yêu cầu; selection không
được confirm làm session mất trạng thái ready và prompt bị refuse. Backend error giữ nguyên
code/message/data. Sau đổi model, nếu effort khác giá trị trước đó thì adapter reapply và confirm
(live 2.33.1 không reset, nhưng Paseo có thể bỏ qua setter khi thinkingOptionId không đổi).

Không launch bằng `--agent`, `--model`, `--effort` hoặc `--trust-*`: V3 reject các flag đó. Adapter
gửi `_meta.kiro.modeId=epistex_<role>` trên `session/new`; model ban đầu lấy từ trường `model` của
agent JSON. Effort mặc định của V3 là `high` (Opus 5.5 trả `medium`): nếu ngoài `low`/`medium`, adapter
pin `low` và confirm trước khi trả response. Kiro có thể trả `session/new` trước khi catalog model
load xong (thiếu `model`/`effortLevel`); adapter đợi `config_option_update` có hai option đó. Load
giữ mode/model/effort đã lưu (kiểm live trong process mới); `config_option_update` hoặc
`current_mode_update` đưa session ra ngoài mode/model/effort cho phép sẽ thu hồi session và gửi
`session/cancel`.

Authentication do CLI giữ (`--auth-method=cli`); adapter không trả `_kiro/auth/getAccessToken`.

## Native topology và role

Peer seat dùng allowlist native tools; **không có `subagent`, `goal` hoặc Paseo MCP** (Lead
giữ đúng một server Paseo injected như trên). New/load
chỉ thành công sau khi mode/model và raw tool inventory đã được kiểm. Load bỏ inventory/session
validation cũ, đợi advertisement mới và kiểm lại inventory ngay trước response thành công;
inventory unsafe xuất hiện trong lúc confirmation làm load thất bại. Runtime installed phải
match byte-for-byte file kit. Workspace `.kiro/agents/epistex_peer.json`/`.md` (kể cả ancestor)
làm launch/session thất bại để tránh workspace override global agent. Không tự sửa override.
Mode switches, native agent/chat/rewind commands, subagent lifecycle và global setting writes
bị reject. Từ extension V3, adapter chỉ relay `_kiro/session/context` và `_kiro/session/compact`
(compact qua cùng prompt gate) khi backend quảng bá, và chỉ quảng bá lại hai method này trong
`initialize`; `_kiro/workflow/*`, memory, export, `_kiro/mcp/*`, `_session/*` (kể cả `_session/steer`),
`session/fork`/`delete`/`list` bị reject `-32601`. `session/close` được relay. Approval vẫn đi qua ACP
permission request với `options[]` của agent; adapter không tự tạo consent. Notifications và unknown metadata giữ nguyên; unsupported agent-to-client requests
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

Probe in raw ACP qua adapter Peer: session mới ở `epistex_peer` với effort đã pin, tag không có
MCP/`subagent`, confirm cả bốn selection, reject `mode`/`high`/`autopilot`/`session/set_mode`; sau
đó load trong cùng process và process mới, kiểm Sonnet/medium còn nguyên. Fixture backend mô phỏng
hành vi V3 đã quan sát live (default `high`, ignored value vẫn success, tag inventory, catalog và MCP
đến muộn) và kiểm role/CWD, effort pin, ignored model/effort, model reset, hidden options/extension,
cancellation, permission relay, unsafe inventory/mode giữa chừng, override, backend rejection và
early exit. Không thay live model smoke tests. Lead chưa có probe tự động: đã kiểm thủ công với
HTTP MCP loopback giả lập Paseo (11 tag, model switch, probe load refuse prompt).

Lead launch bốn profile qua Paseo sau frozen-candidate review; lấy actual session/model/effort,
raw `config_option_update`, `_kiro/tools/didChange` và `_kiro/mcp/status` hoặc chạy metadata probe trên chính
candidate. Trong live task prompt, yêu cầu agent mô tả heading role **đã nhận trong session**,
liệt kê tools thực sự thấy và in `pwd`; không coi đọc lại file prompt là proof injection.
Peer phải nhận `# Peer — independent co-worker`, project CWD, không Paseo/subagent tools.
Live E2E V3 (2026-10-23, CLI 2.33.1, Paseo 0.12.0, sau `paseo reload`): bốn profile `kiro-peer` và
`kiro-lead`/`kiro-supervisor` Sonnet/low đều launch được với đúng mode/model/effort, nhận
`# Common contract` cộng heading role, CWD là project. Peer chỉ có native tools. Catalog Lead có đúng 11
tool `paseo::*`, Supervisor có đúng 15, cả hai không có `speak`. Lead gọi `list_workspaces` mà không bị
hỏi quyền. Live E2E chỉ phủ create/prompt/gọi MCP `list_workspaces`/archive; `session/cancel`,
`session/resume` và `session/load` qua lifecycle Paseo chưa được live-cover. Chưa kiểm qua Paseo thì chỉ kết luận
ACP metadata/fixture verified, không kết luận seat đã được chấp nhận.

Nguồn authoritative (running capabilities thắng ví dụ tài liệu):
[ACP](https://kiro.dev/docs/acp/), [V3 ACP migration](https://kiro.dev/docs/cli/v3/acp-migration/),
[V3 agent config](https://kiro.dev/docs/cli/v3/agent-config/),
[V3 permissions](https://kiro.dev/docs/cli/v3/permissions/), [built-in tools](https://kiro.dev/docs/tools/),
[custom agents](https://kiro.dev/docs/custom-agents/).
A `kiro-supervisor` seat also exists: `role-agent supervisor kiro`, `setup/kiro-supervisor.json`, installed agent `~/.kiro/agents/epistex_supervisor.json`, Supervisor Paseo tool set (keeps `create_workspace`).
