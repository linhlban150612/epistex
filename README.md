# Epistex — standalone agent roles trên Paseo

Epistex là bộ prompt, launcher và CLI điều phối độc lập cho Paseo, không cần cài
Seatworks. Kit cung cấp **5 role × 7 backend = 35 provider/profile** dưới tên
`epx-<role>-<agent>`, cùng desk lưu assignment, handback và outbox ngoài product repo.
Luồng hai seat `codex-lead` / `codex-peer` vẫn được hỗ trợ riêng.

| Role | Trách nhiệm | Paseo MCP trong provider |
|---|---|---|
| Supervisor | Nhận intent từ Human, mở/đóng lane, nhận câu hỏi và cảnh báo | Bật |
| Lead | Giao task, chọn review, yêu cầu rework và quyết định acceptance | Bật |
| Peer | Triển khai trong owned scope, kiểm chứng và bàn giao | Tắt |
| Reviewer | Review candidate được giao, trả findings; không acceptance | Tắt |
| Watcher | Quan sát lane, gửi evidence cho Supervisor và Lead | Tắt |

Backend: **Claude, Codex, Devin, Pi, Amp, GLM, Droid**. Codex nạp prompt bằng
`model_instructions_file`; Claude/Pi dùng native launch instructions. Devin/Amp/GLM/Droid
đi qua ACP proxy, thêm role instructions vào prompt đầu tiên của mỗi session trong
vòng đời proxy — **không phải system prompt**. Droid không hỗ trợ Paseo MCP qua cấu hình này.

Đây là phối hợp giữa các agent cùng Unix user, **không phải OS sandbox**. Read-only và
owned scope là contract/prompt, không chặn shell tùy ý. Tắt MCP không ngăn tuyệt đối
agent gọi CLI. Kit không triển khai đầy đủ gate, incident, merge hay permissions engine
của Seatworks. Kiểm tra cấu hình thành công không chứng minh cả 35 profile launch được.

## Cài standalone profiles

Cần Paseo CLI/daemon đã cấu hình, Python **3.11+**, executable và credentials của backend
muốn dùng. Codex cần Bash và canonical `config.toml`; Git dùng để nhận diện chung root,
subdirectory và linked worktree. Desk dùng `fcntl` (Unix); timer tùy chọn cần Linux user
systemd và Node.js. GLM/Droid launcher dùng `npx` với phiên bản pin trong `setup/role-agent`.

Chạy từ thư mục kit, sau khi cho phép thay đổi cấu hình Paseo:

```bash
python3 setup/install-profiles.py
paseo reload
python3 setup/install-profiles.py --check
```

Installer đọc file config hiện có tại `~/.paseo/config.json` hoặc `PASEO_CONFIG`, giữ
provider/profile không thuộc Epistex, cập nhật 35 entry và sao lưu lần đầu sang
`<config-file>.epistex-backup`. Nó từ chối nếu config có plugin `seatworks-v2`, không
gỡ plugin đó thay bạn. `--check` chỉ kiểm prompt/launcher và cấu hình khớp; không đăng
nhập backend, thử model hay khởi động agent. Installer cũng không tự bật daemon MCP
injection: cấu hình `daemon.mcp.enabled=true` và `daemon.mcp.injectIntoAgents=true`
nếu cần Paseo tools. Provider chỉ bật tools cho Supervisor/Lead.

Mở profile `epx-supervisor-codex` (hoặc backend đã kiểm) trong workspace root của project.
Installer cấp `EPISTEX_DESK` trỏ đến `setup/desk.py`; Supervisor dùng nó để `join` trước
khi mở lane. Agent đang chạy không tự nhận cấu hình provider mới.

**Chỉ cần hai Codex seat:** làm theo [SETUP.md](SETUP.md), merge hai entry từ
`examples/paseo-providers.json`, rồi chạy:

```bash
bash setup/setup-seats.sh
paseo reload
bash setup/setup-seats.sh --check
```

`setup-seats.sh` không cài 35 profile và không tự sửa global config; nó kiểm hai provider
và đặt executable bit khi không có `--check`. Checker cần thêm `jq`. Mẫu chọn Lead
`gpt-5.6-sol/low`, Peer `gpt-5.6-luna/low`; standalone Codex Lead/Peer kế thừa các mẫu này,
các role/backend khác không được kit pin cùng model. Desk chỉ nhận caller có provider
`epx-*`, không nhận hai provider `codex-lead` / `codex-peer`.

## Desk: assignment, handback và review

Supervisor mở lane; desk yêu cầu Paseo tạo Lead trong worktree mới. Peer/Reviewer/Watcher
được route đến workspace của lane. Desk kiểm provider, assignment và CWD của caller;
không tìm thấy đúng một workspace phù hợp thì dừng thay vì đoán.

```text
Human → Supervisor → open-lane → Lead → start-task → Peer
                                  ↑                  │
                                  └── done + evidence┘
                                  │
                                  ├─ start-review → Reviewer → done
                                  ├─ rework → Peer (round mới)
                                  └─ accept
Patrol → Watcher → raise → Supervisor + Lead
Supervisor → close-lane (không merge/push/deploy)
```

| Command | Caller / hiệu lực |
|---|---|
| `join`, `open-lane` | Supervisor đăng ký project, mở lane; `--agent` chọn backend cho Lead |
| `start-task` | Lead tạo một Peer; một task chưa kết thúc giữ writer slot của lane |
| `done` | Peer hoặc Reviewer hiện được giao bàn giao với `--task`, `--round`, `--candidate`, `--summary`, `--checks` |
| `start-review` | Lead tạo Reviewer cho round/candidate đã bàn giao; không review moving HEAD |
| `rework` | Lead tăng round, supersede review cũ, queue brief mới cho Peer |
| `accept` | Lead nhận task đã bàn giao, không còn review đang chạy; Peer phải idle và được archive trước khi nhả writer slot |
| `ask`, `answer` | Peer/Reviewer hỏi Lead; Lead hỏi Supervisor; đúng người nhận trả lời |
| `raise` | Watcher được giao gửi observation tới Supervisor và Lead; không có quyền veto |
| `close-lane` | Supervisor mở lane đóng nó khi không còn task chưa kết thúc; không merge/land/push/deploy |
| `upgrade` | Supervisor giữ snapshot task legacy, gán round và quarantine pending mail thiếu scope; không resume work |
| `retire-watcher` | Supervisor mở lane retire Watcher sai CWD đang idle (hoặc đã archived); patrol sau mới tạo replacement |
| `status`, `patrol` | Inspect desk / thực hiện một lượt điều phối; không cần caller role |

Peer dừng ghi sau handback và chỉ tiếp tục theo round rework hiện tại. Reviewer phải
trả đúng candidate của assignment. Desk kiểm identifier khớp, **không tự chứng minh
commit/checksum tồn tại hay artifact bất biến**. Lead vẫn phải kiểm evidence; review
không phải gate bắt buộc trong code `accept`. Không có command `cut` hoặc command chung
để reconcile `uncertain` / `accept_uncertain`, dù các state đó xuất hiện trong workflow.

Ví dụ handback trong phiên Peer được desk giao (thay các placeholder):

```bash
"$EPISTEX_DESK" done --task T... --round 1 \
  --candidate '<full-commit-SHA-or-snapshot-checksum>' \
  --summary 'Implemented assigned change' --checks 'Tests and evidence'
```

Tra CLI mà không chạy workflow:

```bash
python3 setup/desk.py --help
```

## State, patrol và recovery

Desk lưu ledger/outbox có lock và atomic file replacement tại
`~/.local/share/epistex/desk/<project-path-hash>/ledger.json`. Hash desk dài 16 ký tự,
theo đường dẫn project được chọn; **khác** hash runtime Codex 12 ký tự bên dưới.
Không ghi workflow records vào product Git. `status` không gửi mail/launch agent,
nhưng mở context ledger và có thể tạo/ghi lại file state:

```bash
python3 setup/desk.py status --project /absolute/project
systemctl --user status epistex-patrol.timer
```

`patrol --project /absolute/project` xử lý một project; không có `--project` thì duyệt
mọi ledger có project còn tồn tại. Patrol tạo một Codex Watcher cho mỗi lane mở, báo
Peer/Reviewer idle hoặc lỗi mà chưa handback, gửi mail chỉ khi người nhận idle và loại
bỏ mail có scope task/round/candidate đã lỗi thời. Ledger legacy phải được Supervisor
`upgrade` trước; patrol từ chối gửi mail khi chưa nâng cấp.

**Chỉ chạy installer sau khi cho phép bật tự động hóa trên các ledger hiện có:**

```bash
python3 setup/install-patrol.py
```

Lệnh này ghi user service/timer, chạy `daemon-reload` và `enable --now`. Timer dùng
`OnBootSec=30s` và `OnUnitInactiveSec=30s`; có thể chạy ngay khi bật nếu mốc boot đã qua,
rồi lặp 30 giây sau khi service kết thúc. Đây không phải dry run.
Installer lấy Paseo/Node từ PATH; cần đúng CLI, không phải launcher GUI. Không dùng
đường dẫn có khoảng trắng cho installer hiện tại: systemd quoting còn là known issue.

Launch/send bị mất response được đánh dấu uncertain, không tự retry side effect.
Inspect Paseo trước khi xử lý; không sửa JSON hoặc launch lại mù. `upgrade` và
`retire-watcher` là recovery có side effect, không phải bước tự động khi đọc status.
Không bật lại patrol trên lane cũ chỉ vì unit tests xanh.

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

**Giới hạn CWD cần kiểm khi chạy desk:** `desk.launch` truyền `EPISTEX_PROJECT_ROOT`
bằng ledger root, trong khi lane có worktree riêng. Codex wrapper sẽ `cd` về override
đó. Vì vậy workspace routing của desk không tự chứng minh actual Codex CWD đúng lane;
kiểm phiên thực tế trước khi giao quyền ghi. Không coi runtime identity, ledger root
và per-thread worktree CWD là cùng một thứ.

Sync link tài nguyên dùng chung từ canonical home, parse/round-trip TOML, áp prompt
và tắt `agents.enabled`, `features.multi_agent`, `features.multi_agent_v2`. Với
Peer/Reviewer/Watcher, nó loại MCP server tên `paseo` khỏi config runtime. Canonical
config không bị sửa. Sync giữ private sessions/logs/database, từ chối runtime hoặc
ancestor symlink và preflight xung đột; **chỉ thay `config.toml` là atomic**, toàn bộ
link update không phải transaction.

Resume theo UUID có thể tìm lại runtime cùng role trong cả namespace `epistex` và
`seatworks`, không copy session:

```bash
setup/codex-room supervisor resume '<session-UUID>'
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
| `EPISTEX_PROJECT_ROOT` | Launcher CWD cho Codex; project desk nếu không có `--project` |
| `EPISTEX_CODEX_HOME` | `~/.codex`; nguồn canonical config và tài nguyên dùng chung |
| `EPISTEX_STATE_HOME` | `~/.local/share/epistex/desk`; nơi lưu desk state |
| `EPISTEX_DESK` | Installer gán đường dẫn tuyệt đối đến `setup/desk.py` cho các profile |
| `CODEX_BIN` | Executable Codex; mặc định lookup `codex` trên PATH |
| `PASEO_BIN` | Executable Paseo mà desk gọi; mặc định `paseo` |
| `PASEO_CONFIG` | File config dùng cho profile installer và two-seat checker |
| `PASEO_HOME` | Two-seat checker dùng `<PASEO_HOME>/config.json` nếu không có `PASEO_CONFIG` |

Ba biến `SEATWORKS_PROJECT_ROOT`, `SEATWORKS_CODEX_HOME`, `SEATWORKS_STATE_HOME` là
fallback cho biến `EPISTEX_*` tương ứng; giá trị mới không rỗng được ưu tiên. Runtime
cũ dưới `.codex-runtime/seatworks` được dùng tại chỗ nếu duy nhất khớp project/role.
Cả old/new runtime cùng tồn tại thì ordinary launch báo ambiguous. Không có bulk
migration hay tự chuyển legacy desk state; không xóa/copy dữ liệu để chữa resume.

## Policy, kiểm chứng và file chính

Role prompts giữ hành vi ổn định; `AGENTS.md` của product repo giữ invariant chung;
`WORKSPACE_PROTOCOL.md` là policy điều phối Lead đọc; task brief truyền constraint
cụ thể cho Peer. Giữ log, receipt và ledger ngoài Git. Dùng các template trong
`examples/` theo hygiene của repo đích, không tự commit process documents vào mọi repo.

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests
bash -n setup/codex-room
bash -n setup/setup-seats.sh
git diff --check
```

Tests dùng fixture/config/state tạm, không thay cho kiểm auth, model, backend launch,
actual CWD hoặc live recovery. Các giới hạn còn biết: ACP proxy có thể chờ stdin sau
khi child đã thoát, systemd path quoting, và thiếu recovery command chung cho uncertain
outcomes. Xem [HANDOFF.md](HANDOFF.md) để biết evidence và việc còn lại ở checkpoint;
thông tin live daemon/timer/ledger trong đó là lịch sử, cần inspect lại trước vận hành.

| Đường dẫn | Vai trò |
|---|---|
| `agents/*.md` | Prompt Supervisor, Lead, Peer, Reviewer, Watcher |
| `setup/install-profiles.py` | Cài/kiểm 35 standalone provider và profile |
| `setup/role-agent` | Native launcher Claude/Pi và ACP instruction proxy |
| `setup/codex-room`, `setup/codex-room-sync` | Chọn runtime/resume và sinh Codex config |
| `setup/desk.py` | Role routing, ledger, handback, outbox, patrol và recovery hẹp |
| `setup/install-patrol.py` | Cài và bật user-systemd patrol timer |
| `setup/setup-seats.sh`, `examples/paseo-providers.json` | Luồng hai Codex seat riêng |
| `SETUP.md` | Hướng dẫn chi tiết luồng hai seat và Codex runtime |
| `examples/AGENTS_MD_SNIPPET.md`, `examples/WORKSPACE_PROTOCOL.md` | Template contract/policy cho repo đích |
| `tests/` | Regression tests runtime, desk, profiles và two-seat checker |
| `HANDOFF.md` | Checkpoint triển khai, review, evidence và hạn chế còn lại |
