# SETUP — Codex Lead/Peer trên Paseo

## 1. Đặt kit và project ở đường dẫn ổn định

`<KIT>` là đường dẫn tuyệt đối tới thư mục `epistex`; `<PROJECT>` là repository mà hai seat
sẽ làm việc. Paseo daemon phải chạy dưới đúng user sở hữu Codex home và project.
Mặc định provider dùng working directory của workspace Paseo. Chỉ đặt
`EPISTEX_PROJECT_ROOT` nếu muốn cố định provider vào một project; không giữ đường dẫn repo cũ.
Wrapper giữ launcher/worktree CWD làm working directory của Codex, nhưng nhận diện project Git
bằng shared Git directory nên các thư mục con và linked worktree dùng chung runtime. Ngoài Git,
đường dẫn CWD tuyệt đối là project identity. Vì vậy CWD khác nhau ngoài Git không tự động cùng
runtime. Với `codex resume <session-UUID>` hoặc `codex exec resume <session-UUID>` tường minh,
wrapper tìm rollout hiện có theo UUID và role
trong cả namespace `epistex` và `seatworks`, rồi dùng nguyên runtime đó; không copy session và
không chọn nếu không tìm thấy hoặc có nhiều kết quả.
Để tìm runtime khác project hiện tại, dùng đúng hai dạng trên: UUID ngay sau `resume`,
không đặt options trước command/UUID; đặt options sau UUID. Alias `e resume <UUID>` cũng hỗ trợ.
Runtime Git giữ hash đường dẫn main checkout (với `.git` thông thường). Session cũ được tạo
từ thư mục con/worktree khác phải resume bằng UUID; picker, tên session, `--last` và app-server
chỉ thấy runtime của project hiện tại. Wrapper không tìm ID bên trong RPC của app-server.

## 2. Kiểm tiền đề

```bash
bash --version
python3 --version # cần 3.11+ để kiểm TOML
jq --version
codex --version
paseo daemon status --json
```

Codex home chuẩn mặc định là `~/.codex`. Nếu credential/config thật nằm nơi khác, khai biến
`EPISTEX_CODEX_HOME` trong `env` của cả hai provider.
Các cài đặt cũ có thể tiếp tục dùng `SEATWORKS_PROJECT_ROOT`, `SEATWORKS_CODEX_HOME` và
`SEATWORKS_STATE_HOME`; biến `EPISTEX_*` tương ứng luôn ưu tiên. Runtime cũ dưới
`~/.codex-runtime/seatworks` được dùng tại chỗ khi là kết quả duy nhất phù hợp; không có live
migration và dữ liệu cũ không bị xóa. Nếu nhiều runtime cũ/mới cùng phù hợp, launch dừng để người
vận hành xử lý thay vì chọn tùy ý.

Linux Desktop: nếu `paseo` là symlink tới `/opt/Paseo/Paseo` và `paseo run` mở GUI,
dùng `/opt/Paseo/resources/bin/paseo` cho các lệnh CLI bên dưới. Đây là launcher đi kèm
ứng dụng; không cần đổi symlink hoặc restart daemon để cài hai seat.

## 3. Bật injection Paseo tools

Trong `~/.paseo/config.json`, bảo đảm:

```json
{"daemon":{"mcp":{"enabled":true,"injectIntoAgents":true}}}
```

Quyền theo role nằm ở provider: Lead đặt `paseoTools.enabled=true`, Peer đặt `false`. Không
dùng `injectIntoProviders`; field đó không phải cơ chế policy provider hiện hành.

## 4. Merge hai provider

Merge hai entry trong `examples/paseo-providers.json` vào `.agents.providers` của file Paseo
hiện có. Không thay cả file. Trước khi merge:

- thay `<KIT>` bằng đường dẫn tuyệt đối tới `epistex`;
- nếu cần cố định project, thêm `env.EPISTEX_PROJECT_ROOT` bằng đường dẫn tuyệt đối;
- xóa `_doc`;
- xác nhận model ID bằng `paseo provider diagnostic codex --json` hoặc provider discovery.

Mẫu chọn Lead `gpt-6.1-sol` và Peer `gpt-6-luna`, cùng effort mặc định `low`.
Sao lưu config trước khi merge. Các provider khác và cấu hình daemon phải được giữ nguyên.

`command` phải giữ đúng role `lead` và `peer`.

## 5. Đặt contract và protocol tại project đích

- Dùng `examples/AGENTS_MD_SNIPPET.md` để bổ sung contract chung mà cả Lead và Peer đọc.
- Copy `examples/WORKSPACE_PROTOCOL.md` thành `<PROJECT>/WORKSPACE_PROTOCOL.md`, rồi điền risk,
  authority, task class và review gate riêng của repo. File này dành cho Lead; Peer nhận phần
  constraint cần thiết qua task brief.

Trước khi commit hai file trên, tuân theo hygiene của repo đích. Nếu repo cấm persona/process
document, giữ `WORKSPACE_PROTOCOL.md` local và ignored (hoặc ở vị trí Human quản lý), còn
`AGENTS.md` chỉ chứa product boundary, invariant, canonical docs và verification có giá trị bền.
Không tạo evidence folder, review packet hay status ledger trong Git.

Không nhét policy riêng của repo vào provider Paseo hoặc prompt Peer.

## 6. Dựng và kiểm

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s <KIT>/tests
bash <KIT>/setup/setup-seats.sh
paseo reload
bash <KIT>/setup/setup-seats.sh --check
```

Script không tự sửa global config. Lượt không có `--check` chỉ đặt executable bit cho hai
wrapper; runtime được chuẩn bị khi Paseo khởi động seat. Chỉ thay `config.toml` là atomic,
không phải toàn bộ runtime. Sync preflight xung đột file/symlink trước khi thay đổi, cập nhật
links rồi mới thay config; lỗi I/O hoặc thay đổi đồng thời vẫn có thể để lại một phần links đã đổi.
`--check` thất bại nếu config/provider thiếu hoặc sai model, effort hay quyền tools.
Hỗ trợ `PASEO_HOME` hoặc `PASEO_CONFIG` để kiểm config khác vị trí mặc định.
Checker cần Bash, jq, Python 3.11+, dirname, wc và executable `${CODEX_BIN:-codex}`;
lượt đặt executable bit còn cần chmod. Không cần Paseo trên PATH cho kiểm tra tĩnh.
Nếu dùng `CODEX_BIN`, đặt cùng giá trị trong môi trường checker và hai provider.
Kết quả hợp lệ không chứng minh auth, daemon, model khả dụng hoặc launch thành công;
kiểm CLI ở bước 2 và launch ở bước 7 là các kiểm tra riêng.

## 7. Chứng minh cô lập

Khởi động một agent `codex-peer`, yêu cầu nó in dòng đầu prompt role đang đọc; kết quả phải là
`# Peer — independent co-worker`. Làm tương tự với `codex-lead`, kết quả bắt đầu bằng `# Lead`.

Kiểm thêm:

```bash
find ~/.codex-runtime/epistex -maxdepth 3 -name config.toml
```

Hai role phải có runtime riêng. `auth.json`, `skills`, `plugins` là symlink; `config.toml` là
bản generated riêng chứa `model_instructions_file` trỏ về prompt trong kit. Trong mỗi config,
`[agents].enabled`, `[features].multi_agent` và `[features].multi_agent_v2` phải đều là `false`;
Paseo là chủ duy nhất của topology. Sync không xóa session, log, database hoặc private state khác
trong runtime và từ chối ghi nếu đường dẫn runtime của role là symlink.
Các thư mục cha symlink cũng bị từ chối. Sync parse TOML thành cấu trúc, áp policy rồi kiểm
round-trip toàn bộ giá trị trước khi ghi. TOML không hợp lệ hoặc sai kiểu bảng policy làm launch
thất bại trước khi đổi runtime. Bản generated dùng inline tables, không giữ comment/format;
giá trị ngoài policy được giữ nguyên, kể cả chuỗi nhiều dòng. File canonical không bị sửa.

Đây là tách state và quyền MCP, không phải sandbox chống agent độc hại: hai role chạy cùng
Unix user, chia sẻ skills/plugins và vẫn có shell. Peer bị cấm gọi Paseo theo prompt; việc
ẩn Paseo MCP không ngăn tuyệt đối một shell gọi CLI.

## 8. Vận hành

Lead luôn tạo Peer bằng provider `codex-peer`; không dùng provider Codex gốc. Truyền rõ
`modeId` và `thinkingOptionId` khi tạo agent. Agent đang chạy không tự nhận thay đổi provider;
sau khi sửa `~/.paseo/config.json`, chạy `paseo reload` và tạo phiên mới.

Prompt trong kit có trần kỷ luật 16 KiB. Sửa xong chạy lại `setup-seats.sh --check`.

## 9. Hai seat Claude riêng

Giữ nguyên contract/protocol và các bước backup, merge, MCP injection, reload, live verification
ở trên. Không dùng `codex-room` cho Claude, không cần cài cả 21 standalone profile.
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

`setup-seats.sh --check` chỉ kiểm hai Codex provider, không chứng minh Claude đã cài đúng.
Kiểm riêng field hai Claude provider, chạy regression suite và launch cả hai role.
Đây là role/MCP separation, không phải OS sandbox hay hai credential home cô lập.

## 10. Hai seat Amp riêng qua ACP

Dùng các bước backup, merge, MCP injection, contract/protocol, reload và live verification
ở trên. Cần executable `amp-acp` và tài khoản Amp đã đăng nhập. Kiểm discovery bằng
`paseo provider models amp-acp --json` và `paseo provider diagnostic amp-acp --json`.
Adapter có thể không hỗ trợ `--version`; diagnostic ACP initialize/session mới và launch
thực tế là kiểm tra riêng, không coi lỗi version command là bằng chứng launch thất bại.

Merge hai provider vào `.agents.providers`, không thay provider `amp-acp` hiện có:

| Field | `amp-lead` | `amp-peer` |
|---|---|---|
| `extends` | `acp` | `acp` |
| `command` | `["<KIT>/setup/role-agent", "lead", "amp"]` | `["<KIT>/setup/role-agent", "peer", "amp"]` |
| `enabled` | `true` | `true` |
| `env` | `{}` | `{}` |
| `paseoTools.enabled` | `true` | `false` |
| `models[0].id` | `medium` | `low` |
| `models[0].label` | `Medium` | `Low` |
| `models[0].isDefault` | `true` | `true` |

`medium`/`low` ở đây là model ID mà Amp ACP expose qua Paseo, không phải thinking option
riêng. Không thêm `thinkingOptions` giả. Chọn permission mode từ discovery (adapter hiện
có `default` và `bypass`); dùng `default` cho smoke test. Thay `<KIT>` bằng đường dẫn tuyệt
đối, giữ `role-agent` executable, rồi chạy `paseo reload` và tạo phiên mới.

ACP proxy thêm role instructions vào prompt đầu tiên của mỗi session trong vòng đời proxy,
không phải system prompt. Kiểm heading Lead/Peer từ nội dung session agent thực sự nhận,
CWD thực tế và tool inventory: Lead phải gọi được một Paseo tool read-only; Peer không thấy
Paseo tools. Không yêu cầu agent đọc file prompt rồi coi đó là proof injection.
Lead điều phối bằng `amp-peer`, không dùng provider Amp gốc; không bật desk/patrol cho hai seat.

`setup-seats.sh --check` vẫn chỉ kiểm Codex. Kiểm riêng hai Amp provider và live launch;
không thay global Amp config, credentials hoặc state để tạo role separation.

## 11. Pi Peer và OMP Peer riêng

Dùng các bước backup, merge, protocol, reload và live verification ở trên. Không cần cài
21 standalone profile. Kiểm executable `pi`, `omp`, auth của backend và discovery bằng
`paseo provider models pi --json`, `paseo provider models omp --json` trước khi cấu hình.
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
| `models[0].thinkingOptions` | `[{"id":"medium","label":"Medium","isDefault":true}]` | `[{"id":"max","label":"Max","isDefault":true}]` |

`medium`/`max` là effort mặc định discovery tại lần cài này khi Human không chỉ định effort;
kiểm lại discovery trước lần cài khác. Thay `<KIT>` bằng đường dẫn tuyệt đối, giữ launcher
executable, chạy `paseo reload` và tạo phiên mới với model/effort và mode từ discovery.
Launcher dùng native `--append-system-prompt <KIT>/agents/PEER.md`, chuyển tiếp RPC args
và stdin nguyên trạng, giữ CWD và auth home hiện có; không dùng ACP proxy cho hai backend này.

Kiểm phiên thực tế: heading từ active instructions phải là `# Peer — independent co-worker`,
`pwd` đúng workspace, model/effort đúng và không có Paseo tools trong inventory kể cả deferred
discovery nếu có. Không đọc file role để thay bằng chứng injection. Diagnostic không thay thế
live launch. `setup-seats.sh --check` vẫn chỉ kiểm Codex; kiểm riêng hai provider này.
Chỉ dùng `pi-peer`/`omp-peer` để điều phối khi Human cho phép delegation. Không bật desk/patrol,
không xóa session hay thay credentials; role/MCP separation không phải OS sandbox.

## 12. Devin Lead/Peer, GitHub Copilot Peer và Cursor Peer qua ACP

Backup và merge vào `.agents.providers`, không thay các backend gốc hay credential/config
home của chúng. Kiểm executable, auth và discovery của `devin`, `copilot`, `cursor` trước.
Giữ MCP injection bật ở daemon, nhưng chỉ Devin Lead được expose Paseo tools.

| Provider | `command` (thay `<KIT>` bằng đường dẫn tuyệt đối) | Model ID | Thinking mặc định | Paseo tools |
|---|---|---|---|---|
| `devin-lead` | `["<KIT>/setup/role-agent","lead","devin"]` | `fusion-claude-fable-5-1-medium-sidekick-swe-2-medium` | `medium` | Bật |
| `devin-peer` | `["<KIT>/setup/role-agent","peer","devin"]` | `fusion-claude-opus-5-5-high-sidekick-swe-2-medium` | `high` | Tắt |
| `copilot-peer` | `["<KIT>/setup/role-agent","peer","copilot"]` | `gpt-6-luna` | `medium` | Tắt |
| `cursor-peer` | `["<KIT>/setup/role-agent","peer","cursor"]` | `composer-2.5[fast=true]` | Không có | Tắt |

Cả bốn entry dùng `extends: "acp"`, `enabled: true`, `env: {}` và `paseoTools.enabled`
theo bảng. Đặt `models: [{"id":"<MODEL>","label":"<LABEL>","isDefault":true}]`; với
Devin/Copilot thêm `thinkingOptions: [{"id":"<EFFORT>","label":"<LABEL>","isDefault":true}]`
vào model theo bảng. Không thêm thinking option cho Composer 2.5.

ID rút gọn `fusion-claude-fable` không xuất hiện trong discovery tại lần cài này; ID đầy đủ
ở bảng đúng tên Fusion (Claude Fable 5.1 Medium + SWE-2 Medium). Discovery summary báo
Devin effort mặc định `medium`, nhưng phiên Fusion Opus High thực tế báo `high`; giữ `high`
để khớp biến thể được yêu cầu. Cursor summary trả ID trần `composer-2.5`, nhưng ACP session
catalog/set-model yêu cầu `composer-2.5[fast=true]`; ID trần bị từ chối và phiên đầu vẫn ở
`default[]`. Kiểm lại catalog của phiên và metadata sau launch, không chỉ discovery summary.

Launcher chạy `devin acp`, `copilot --acp`, `cursor-agent acp`; dùng proxy ACP hiện có để
thêm role instructions vào prompt đầu tiên của mỗi session, không phải system prompt.
Không thêm project policy vào provider hoặc sửa global instructions của backend.
Sau reload, tạo phiên mới với model/effort và mode thực tế từ discovery. ACP hiện trả Devin
mode `accept-edits`, Copilot `https://agentclientprotocol.com/protocol/session-modes#agent`,
Cursor `agent` cho phiên smoke test; không suy ra mode ID `default` từ nhãn/default summary.

Kiểm heading role từ context agent thực sự nhận, CWD bằng `pwd`, model/effort và inventory
kể cả deferred discovery nếu có. Devin Lead phải gọi thành công một Paseo MCP tool read-only;
các Peer không thấy Paseo tools. Không dùng shell CLI thay bằng chứng MCP. Không bật desk,
patrol hoặc delegation trong smoke test. Native tool/subagent của backend không đồng nghĩa
với Paseo MCP; role/tool visibility không phải OS sandbox. Checker Codex và diagnostic
không thay thế live verification của bốn seat này.

Nếu Cursor trả `Upgrade your plan to continue` sau khi metadata đã chọn đúng Composer,
đó chưa phải phiên smoke test thành công. Giữ model yêu cầu, báo giới hạn tài khoản và kiểm
lại sau khi Human xử lý quyền sử dụng; không tự chuyển Auto hay nâng cấp gói để vượt lỗi.
