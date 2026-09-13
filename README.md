# Epistex — Codex Lead/Peer trên Paseo

Bộ kit dựng hai seat Codex độc lập trên một project:

- `codex-lead`: framing, giao việc, review và acceptance; có Paseo tools.
- `codex-peer`: triển khai, evidence và handoff; không có Paseo tools.

Mỗi seat chạy qua wrapper, nhận một `CODEX_HOME`
riêng; credential, skills và plugins được chia sẻ từ Codex home chuẩn bằng symlink; còn quyền
sửa, delegation, verification và bàn giao được quyết định tường minh theo từng yêu cầu.

Ba lớp policy không trộn vào nhau:

- prompt seat giữ hành vi ổn định của Lead/Peer;
- `WORKSPACE_PROTOCOL.md` giữ chiến thuật điều phối riêng của repo và chỉ Lead đọc;
- task brief giữ assignment cụ thể mà Peer cần thực hiện.

Các artifact điều phối tạm thời không trở thành rác trong product repository. `AGENTS.md` nên
ngắn và nêu invariant thật; tài liệu chỉ cập nhật trong canonical set của repo; log, receipt,
review packet và status ledger ở ngoài Git. `WORKSPACE_PROTOCOL.md` có thể là file local/ignored
nếu repository không cho phép commit process document.

```text
Paseo provider
  → setup/codex-room <lead|peer>
  → setup/codex-room-sync
  → ~/.codex-runtime/seatworks/<project-id>/<role>/
       config.toml       (bản runtime, prompt riêng theo role)
       auth.json         → ~/.codex/auth.json
       skills, plugins   → ~/.codex/{skills,plugins}
  → codex chạy tại project đích
```

Kit phân biệt ba loại state: prompt và wrapper trong repo là **canonical**; `config.toml` dưới
runtime là **generated** và được ghi atomically trước mỗi lần launch; session/log/database còn
lại trong runtime là **private mutable state** và sync không xóa. Symlink chỉ dùng cho tài
nguyên cá nhân được chia sẻ. Sync từ chối role runtime nếu chính đường dẫn đó là symlink và ép
cả native Codex agents lẫn multi-agent feature về `false`, để Paseo là chủ duy nhất của topology.

## Dùng nhanh

Đọc và làm theo [SETUP.md](SETUP.md). Sau khi merge provider vào Paseo:

```bash
bash setup/setup-seats.sh
paseo reload
bash setup/setup-seats.sh --check
```

Prompt nằm tại `agents/LEAD.md` và `agents/PEER.md`; Codex nạp chúng bằng
`model_instructions_file`. Cấu hình mặc định: Lead `gpt-5.6-sol/low`, Peer `gpt-5.6-luna/low`.

## File chính

| Đường dẫn | Vai trò |
|---|---|
| `SETUP.md` | Quy trình cài và tiêu chí hoàn tất |
| `agents/LEAD.md`, `agents/PEER.md` | Prompt của hai seat |
| `setup/codex-room` | Wrapper Paseo gọi để khởi động Codex |
| `setup/codex-room-sync` | Sinh runtime `CODEX_HOME` cô lập, idempotent |
| `setup/setup-seats.sh` | Kiểm tra bộ kit và provider đã merge |
| `examples/paseo-providers.json` | Hai provider mẫu để merge |
| `examples/AGENTS_MD_SNIPPET.md` | Khung contract dùng chung trong repo đích |
| `examples/WORKSPACE_PROTOCOL.md` | Khung policy điều phối riêng của repo dành cho Lead |
