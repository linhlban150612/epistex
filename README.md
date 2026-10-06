# Epistex — standalone agent roles trên Paseo

Epistex là bộ prompt và launcher role cho Paseo, không cần cài Seatworks. Kit cung cấp
Lead/Peer Codex và Supervisor Devin ACP; Paseo là control plane duy nhất. Không còn
desk, installer 21 provider, patrol hay profile `epx-*`.

| Role | Trách nhiệm | Paseo MCP trong provider |
|---|---|---|
| Supervisor | Quan sát liên dự án, mở Lead và hỗ trợ Human; không nhận/đánh giá artifact | Bật |
| Lead | Giao task, yêu cầu rework và quyết định acceptance | Bật |
| Peer | Triển khai trong owned scope, kiểm chứng và bàn giao | Tắt |

Lead chỉ điều phối: yêu cầu triển khai của Human mặc định cấp quyền tự giao Peer và
review/rework trong scope, trừ khi Human giới hạn delegation. Peer là writer duy nhất
cho implementation, test, config, tài liệu và giải quyết conflict, kể cả việc một dòng.
Lead đọc, kiểm chứng và accept/rework; Peer bị chặn thì Lead báo blocked, không tự viết thay.
Yêu cầu read-only không tự cấp quyền tạo agent; delegation không cấp quyền bật automation,
đổi model/effort, push hay deploy.

Backend: **Claude, Codex, Devin, Pi, Amp, GLM, Droid**. Codex nạp prompt bằng
`model_instructions_file`; Claude thêm role vào `appendSystemPrompt` của bản tin SDK
`initialize` khi chạy stream-json, hoặc dùng `--append-system-prompt` ngoài SDK;
Pi dùng native launch instructions. Devin/Amp/GLM/Droid
đi qua ACP proxy, thêm role instructions vào prompt đầu tiên của mỗi session trong
vòng đời proxy — **không phải system prompt**. Droid không hỗ trợ Paseo MCP qua cấu hình này.

Đây là phối hợp giữa các agent cùng Unix user, **không phải OS sandbox**. Read-only và
owned scope là contract/prompt, không chặn shell tùy ý. Tắt MCP không ngăn tuyệt đối
agent gọi CLI. Kit không triển khai đầy đủ gate, incident, merge hay permissions engine
của Seatworks. Kiểm tra cấu hình thành công không chứng minh mọi backend launch được.

## Cài các seat Codex và Supervisor

Cần Paseo CLI/daemon đã cấu hình, Python **3.11+**, executable và credentials của backend
muốn dùng. Codex cần Bash và canonical `config.toml`; Git dùng để nhận diện chung root,
subdirectory và linked worktree.

Chạy từ thư mục kit, sau khi cho phép thay đổi cấu hình Paseo:

```bash
bash setup/setup-seats.sh --check
```

Merge ba entry trong `examples/paseo-providers.json` vào `.agents.providers` của config
hiện có; thay `<KIT>` bằng đường dẫn tuyệt đối và bỏ `_doc`. Đừng thay cả file config.
Đặt MCP injection bật; provider bật tools cho Lead và Supervisor, tắt cho Peer.
Supervisor chỉ chạy trong workspace rỗng `~/work/SUPERVISOR`; prompt kiểm tra CWD
chính xác. Supervisor khám phá workspaces, agents, providers và models qua Paseo, không
dùng registry.

Lead/Peer Codex và runtime safeguards được mô tả trong [SETUP.md](SETUP.md). Chạy:

```bash
bash setup/setup-seats.sh
paseo reload
bash setup/setup-seats.sh --check
```

`setup-seats.sh` không tự sửa global config; nó kiểm ba seat và đặt executable bit khi
không có `--check`. Checker cần thêm `jq`. Mẫu chọn Lead
`gpt-6.1-sol/low`, Peer `gpt-6-luna/low`; Supervisor dùng Devin ACP model/effort đã chọn
trong provider table. Không đưa policy riêng của project vào provider config.

## Luồng Paseo-only

Supervisor quan sát qua Paseo; Lead owns topology, routing, review và acceptance. Peer là
writer duy nhất. Supervisor mở Lead trong workspace project, không tự tạo Peer.

| Bước | Control plane / owner |
|---|---|
| Discovery | Supervisor dùng Paseo `list_workspaces`, `list_agents`, `list_providers`, `list_models` |
| Assignment | Supervisor mở Lead được Human cho phép bằng `create_agent(workspaceId=...)`; truyền agentId Supervisor trong initialPrompt |
| Execution | Lead xác định scope và tạo Peer bằng Paseo; Peer là writer duy nhất |
| Handoff | Peer gửi đủ sáu cell trực tiếp cho Lead, kèm candidate identity |
| Review | Lead đọc chính xác candidate và evidence; Human review khi risk cao |
| Rework | Lead gửi đúng một `send_agent_prompt` nêu task, round, base SHA, candidate bị từ chối và feedback |
| Acceptance | Lead quyết định; Supervisor không nhận thay |
| Archive | Supervisor archive Lead khi Human xác nhận project đóng |

Không có desk, registry, ledger, patrol, timer, schedule hay heartbeat. Paseo messages là
đường giao tiếp; trạng thái idle/notification không chứng minh hoàn tất.

## Codex runtime và resume

```text
Paseo provider → setup/codex-room <role> → setup/codex-room-sync
  → ~/.codex-runtime/epistex/<project-id>/<role>/
       config.toml          generated, prompt theo role
       auth.json            → canonical Codex home
       skills/, plugins/    → canonical Codex home
       sessions/logs/...    private mutable state
  → Codex tại working directory wrapper đã chọn
```

Git root, subdirectory và linked worktree dùng chung runtime theo role qua shared Git
directory; layout `.git` thông thường giữ hash đường dẫn main checkout cũ. Ngoài Git
(hoặc khi không có Git), identity theo đường dẫn tuyệt đối. `EPISTEX_PROJECT_ROOT`, nếu
có, chọn **cả project lẫn CWD launch**; nếu không thì dùng launcher `$PWD`.

Sync link tài nguyên dùng chung từ canonical home, parse/round-trip TOML, áp prompt
và tắt `agents.enabled`, `features.multi_agent`, `features.multi_agent_v2`. Với
Peer, nó loại MCP server tên `paseo` khỏi config runtime. Canonical
config không bị sửa. Sync giữ private sessions/logs/database, từ chối runtime hoặc
ancestor symlink và preflight xung đột; **chỉ thay `config.toml` là atomic**, toàn bộ
link update không phải transaction.

Resume theo UUID có thể tìm lại runtime cùng role trong cả namespace `epistex` và
`seatworks`, không copy session:

```bash
setup/codex-room peer exec resume '<session-UUID>' --json 'Continue the assigned task'
```

Dùng UUID ngay sau `resume`, đặt options sau UUID, không trước command/UUID; alias
`e resume <UUID>` cũng hỗ trợ. Không có hoặc nhiều runtime khớp thì dừng. Picker,
tên session, `--last` và các layout argument khác chỉ dùng runtime project hiện tại.
Wrapper **không đọc session ID trong app-server RPC**; sửa routing CLI không chứng
minh old Supervisor trong Paseo đã resume được.

### Biến môi trường và tương thích Seatworks

| Biến | Mặc định / mục đích |
|---|---|
| `EPISTEX_PROJECT_ROOT` | Launcher CWD cho Codex khi project cần pin |
| `EPISTEX_CODEX_HOME` | `~/.codex`; nguồn canonical config và tài nguyên dùng chung |
| `CODEX_BIN` | Executable Codex; mặc định lookup `codex` trên PATH |
| `PASEO_CONFIG` | File config dùng cho seat checker |
| `PASEO_HOME` | Seat checker dùng `<PASEO_HOME>/config.json` nếu không có `PASEO_CONFIG` |

Hai biến `SEATWORKS_PROJECT_ROOT`, `SEATWORKS_CODEX_HOME` là
fallback cho biến `EPISTEX_*` tương ứng; giá trị mới không rỗng được ưu tiên. Runtime
cũ dưới `.codex-runtime/seatworks` được dùng tại chỗ nếu duy nhất khớp project/role.
Cả old/new runtime cùng tồn tại thì ordinary launch báo ambiguous. Không có bulk
migration; không xóa/copy dữ liệu để chữa resume.

## Policy, kiểm chứng và file chính

Role prompts giữ hành vi ổn định; `AGENTS.md` của product repo giữ invariant chung;
`WORKSPACE_PROTOCOL.md` là policy điều phối Lead đọc; task brief truyền constraint
cụ thể cho Peer. Giữ log và receipt ngoài Git. Dùng các template trong
`examples/` theo hygiene của repo đích, không tự commit process documents vào mọi repo.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
bash -n setup/codex-room
bash -n setup/setup-seats.sh
git diff --check
```

Tests dùng fixture/config/state tạm, không thay cho kiểm auth, model, backend launch,
actual CWD hoặc live recovery. `HANDOFF.md` ghi các giới hạn từng được quan sát, nhưng
không xác nhận chúng còn tồn tại; kiểm tra code và fixture hiện hành trước khi dựa vào
đó. Thông tin daemon/timer/ledger và kế hoạch lịch sử không phải trạng thái hiện tại;
kiểm tra trạng thái live trước khi vận hành.

| Đường dẫn | Vai trò |
|---|---|
| `agents/*.md` | Prompt Supervisor, Lead, Peer |
| `setup/role-agent` | Native launcher Claude/Pi và ACP instruction proxy |
| `setup/codex-room`, `setup/codex-room-sync` | Chọn runtime/resume và sinh Codex config |
| `setup/setup-seats.sh`, `examples/paseo-providers.json` | Ba role seat và provider check |
| `SETUP.md` | Hướng dẫn role seats và Codex runtime |
| `examples/AGENTS_MD_SNIPPET.md`, `examples/WORKSPACE_PROTOCOL.md` | Template contract/policy cho repo đích |
| `tests/` | Regression tests runtime, role launchers và seat checker |
| `HANDOFF.md` | Checkpoint lịch sử; không phải hướng dẫn vận hành hiện tại |
