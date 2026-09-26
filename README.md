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
  → ~/.codex-runtime/epistex/<project-id>/<role>/
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

## 35 standalone role profiles

Without installing Seatworks, run `python3 setup/install-profiles.py`, then `paseo reload`,
then `python3 setup/install-profiles.py --check`. This adds five roles (Supervisor, Lead,
Peer, Reviewer, Watcher) across Claude, Codex, Devin, Pi, Amp, GLM and Droid, under
`epx-<role>-<agent>` names. The installer preserves other providers and profiles and saves
the original Paseo config to `~/.paseo/config.json.epistex-backup` on its first run.
Codex uses project/role-isolated `CODEX_HOME` and native instructions; Claude and Pi
receive native launch instructions. For Devin, Amp, GLM and Droid an ACP proxy prepends
role instructions to the first prompt of each session. That is *not* a system prompt.
The standalone desk below routes by role, but does not provide Seatworks' full gate,
incident, merge, or permissions engine or an OS sandbox. Reviewer/Watcher are instructed
to be read-only but cannot be relied on as a security boundary.
Provider readiness only checks that the launcher exists: actual launches still require each
agent's own login/API credentials, and Droid does not expose Paseo MCP tools.
This setup does not touch Seatworks' source or state.

### Desk workflow

`python3 setup/install-patrol.py` installs and enables a **user-level systemd timer**
that runs `setup/desk.py patrol` every 30 seconds. The desk stores its own private,
locked, atomically written ledger and outbox under `~/.local/share/epistex/desk/`;
it never writes workflow records into the product repository. Start a **Supervisor**
profile in the project's root workspace and give it your intent. Its prompt instructs
it to call `"$EPISTEX_DESK" join`, then `open-lane` once you authorize the work.
The desk creates a Lead in a Paseo worktree; Lead uses `start-task` for one Peer at a
time, Peer calls `done`, Lead may use `start-review`, then `accept` or `rework`.
`ask`/`answer` route questions. Patrol delivers outbox mail only to idle agents,
reports a Peer idle without a hand-back, and starts one Codex Watcher for each open lane;
Watcher can `raise` an observation to Supervisor and Lead. `close-lane` marks a lane
closed but **does not merge, land, push or deploy**. Human decides those actions.

Inspect safely with `setup/desk.py status --project /absolute/project` and
`systemctl --user status epistex-patrol.timer`. If a launch or mail delivery is
marked **uncertain**, inspect Paseo manually; the desk never retries an uncertain
side effect. The desk is for trusted agents under the same Unix user, not an access
control boundary. Native Seatworks parallel lanes, automatic merges, sensor findings,
and incident handling are deliberately not emulated.

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
