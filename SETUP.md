# SETUP — Codex Lead/Peer trên Paseo

## 1. Đặt kit và project ở đường dẫn ổn định

`<KIT>` là đường dẫn tuyệt đối tới thư mục `epistex`; `<PROJECT>` là repository mà hai seat
sẽ làm việc. Paseo daemon phải chạy dưới đúng user sở hữu Codex home và project.
Mặc định provider dùng working directory của workspace Paseo. Chỉ đặt
`SEATWORKS_PROJECT_ROOT` nếu muốn cố định provider vào một project; không giữ đường dẫn repo cũ.

## 2. Kiểm tiền đề

```bash
bash --version
python3 --version # cần 3.11+ để kiểm TOML
jq --version
codex --version
paseo daemon status --json
```

Codex home chuẩn mặc định là `~/.codex`. Nếu credential/config thật nằm nơi khác, khai biến
`SEATWORKS_CODEX_HOME` trong `env` của cả hai provider.

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
- nếu cần cố định project, thêm `env.SEATWORKS_PROJECT_ROOT` bằng đường dẫn tuyệt đối;
- xóa `_doc`;
- xác nhận model ID bằng `paseo provider diagnostic codex --json` hoặc provider discovery.

Mẫu chọn Lead `gpt-5.6-sol` và Peer `gpt-5.6-luna`, cùng effort mặc định `low`.
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
python3 -m unittest discover -s <KIT>/tests -v
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
find ~/.codex-runtime/seatworks -maxdepth 3 -name config.toml
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
