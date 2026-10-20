# epistex: kế hoạch v3 cho repo do agent bảo trì

Ngày: 20/10/2026, 9:25 (giờ VN). HEAD: `a61c56d` (origin/main). Không có commit mới so với v2.
Chỉ đọc repo. Không sửa code. Không commit. Không push. Không mở PR.

## 0. Kết quả chính

- Repo không đổi từ 19/10. Mọi bằng chứng file:line của v2 vẫn đúng.
- Test: 98 pass, 1 skip, 254 subtest pass, 72 giây. Kết quả bằng lần trước (99 = 98 pass + 1 skip).
- KEEP: 4/4 nguyên tắc đã xong.
- SLIM: 3 nguyên tắc làm một phần (S1–S3). 2 nguyên tắc còn thiếu (S4, S5).
- Mới từ X (7 ngày): lỗi lặp lại phải thành hook hoặc test. AGENTS.md cần có owner và ngày review. AGENTS.md phải ngắn.

## 1. Hiện trạng repo

- `LEAD.md` 16.355 ký tự, `PEER.md` 9.908 ký tự, `SUPERVISOR.md` 4.823 ký tự. LEAD và PEER vượt trần 8.000.
- `AGENTS.md` 38 dòng. Nó gọn và đúng hướng. Nó chưa có owner và ngày review.
- Chưa có `.gitignore`. `git status` còn `setup/__pycache__/`, `tests/__pycache__/` sau khi chạy test.
- Chưa có CI, hook, CODEOWNERS.
- `AGENTS.md:28` và `README.md:69,75` cấm timer, heartbeat, polling. Kế hoạch giữ quy tắc này.

## 2. KEEP: trạng thái

| Nguyên tắc | Bằng chứng | Trạng thái |
|---|---|---|
| Supervisor quan sát, Lead quyết, Peer viết | `README.md:13,43,53-56`; `SUPERVISOR.md:37-40`; `LEAD.md:44` | Xong |
| Một writer cho mỗi scope | `LEAD.md:44`; cổng dừng writer `LEAD.md:192,247`; `SUPERVISOR.md:60`; `README.md:75` | Xong |
| Candidate cố định | `LEAD.md:133`; `PEER.md:141`; `LEAD.md:256` | Xong |
| Review độc lập cho việc rủi ro cao | `LEAD.md:148-164`; `README.md:52,66`; `.agents/skills/dual-lane-review/SKILL.md:13` | Xong |

Lỗ hổng: quy tắc lặp ở 4 file (LEAD, PEER, SUPERVISOR, README). Lặp làm lệch nội dung khi một agent chỉ sửa một file.

## 3. SLIM: trạng thái

| # | Nguyên tắc | Trạng thái | Bằng chứng | Thiếu |
|---|---|---|---|---|
| S1 | Một profile mặc định cho mỗi role | Một phần | `LEAD.md:74-81` | Chưa có file nêu profile mặc định. `examples/paseo-providers.json` quá lớn. |
| S2 | Human duyệt trước profile phụ và cặp review khác họ model | Một phần | `LEAD.md:78`; `README.md:66`; `SKILL.md:13` | Chưa có danh sách đã duyệt. |
| S3 | Hai lane chỉ khi rủi ro cần | Một phần | `LEAD.md:149-151,160-164`; `SKILL.md:36` | Tiêu chí "complex/review" nằm ở `WORKSPACE_PROTOCOL.md`, ngoài repo. |
| S4 | Workspace nền cho việc phụ; khôi phục tìm cả workspace nền | Thiếu | `README.md:48`; `LEAD.md:186-199` | Repo không nhắc "background workspace". Cổng dừng writer có thể bỏ sót writer nền. |
| S5 | Không archive workspace để dọn sidebar | Thiếu | `README.md:57`; `SUPERVISOR.md:27`; `LEAD.md:256` | Không có câu cấm. Chữ "archive ... abandoned agents" dễ bị hiểu rộng. |

## 4. Luật phần mềm → thay đổi cụ thể

| Luật | Thay đổi trong repo |
|---|---|
| Conway; Single Responsibility | Giữ 3 role. Thêm `agents/COMMON.md` giữ quy tắc chung một lần. |
| DRY / Single source of truth | 4 file trỏ tới `COMMON.md`. Test kiểm mỗi quy tắc có một nguồn. |
| Gall (hệ phức tạp lớn lên từ hệ đơn giản) | Một Peer mặc định. Hai lane chỉ theo tiêu chí S3. |
| Postel / Design by Contract | Parser handoff 6 ô. Thiếu `Verification` thì fail. |
| Goodhart | Đo cả adherence lẫn effect trên task bank. Không chỉ đếm test. |
| Murphy; Fail fast | Cổng `BLOCKED` khi không có cặp review hợp lệ hoặc writer nền chưa dừng. |
| Hyrum | Test khóa tên tool Paseo và cú pháp handoff. |
| Lehman (phần mềm phải được bảo trì liên tục) | AGENTS.md có owner và ngày review. Lỗi lặp ≥ 2 lần thành hook hoặc test. |
| Brooks; Amdahl | Hai writer song song chỉ khi scope tách rời và có worktree riêng. |
| Chesterton's fence | Prompt ghi lý do cho mỗi cấm đoán (ledger, heartbeat, archive). |
| Kernighan; Miller (7±2) | LEAD và PEER ≤ 8.000 ký tự. File ≤ 5.000 token. |

## 5. Roadmap

### P0: văn bản và gate (1–2 ngày, cần bạn duyệt)
1. Áp S4 và S5 vào `LEAD.md`, `SUPERVISOR.md`, `README.md:57`. Đây là hai lỗ hổng có rủi ro. Kiểm: test chuỗi "background workspace" và "Do not archive workspaces".
2. Áp S1–S3: `examples/default-profiles.json` (≤ 1 KB), mục `approved-profiles` trong `SETUP.md`, tiêu chí hai lane tại `LEAD.md:160`.
3. `.gitignore` cho `__pycache__/`, `.pytest_cache/`, log. Kiểm: `git status` sạch sau test.
4. `scripts/verify` gộp 3 lệnh ở `AGENTS.md:33-34`. Kiểm: exit ≠ 0 khi có lỗi cú pháp.
5. Hook chặn file staged > 5.000 token.

### P1: prompt nhỏ (3–4 ngày)
1. `agents/COMMON.md` giữ KEEP một lần.
2. Tách PEER, rồi LEAD: contract ≤ 8.000 ký tự, phần còn lại thành skill. Kiểm: test đếm ký tự; chạy Paseo thật.
3. Parser handoff 6 ô.
4. `AGENTS.md`: thêm owner, ngày review, dòng ASD-STE100.
5. Tách 6 file > 5.000 token.

### P2: đo và ownership (3–4 ngày)
1. CI chạy `scripts/verify`. CẢNH BÁO: hạ tầng chung, cần bạn duyệt.
2. CODEOWNERS cho `agents/`, `AGENTS.md`. CẢNH BÁO: cần bạn duyệt.
3. Gate: CI fail khi số test giảm (mốc 98 + 1 skip).
4. Task bank 5–10 task: rework trước handback, thay writer khi chưa dừng, writer ở workspace nền, cặp review cùng họ.
5. Quy tắc "lỗi lặp ≥ 2 lần thành hook hoặc test", ghi trong `AGENTS.md`.
6. Tùy chọn: trace ngoài Git. CẢNH BÁO: đảo `README.md:69`.

P3 của v2 (Harness², collector Hermes/Reason, mutation test) giữ nguyên.

## 6. Bạn cần chốt
1. Duyệt văn bản S1–S5? S4 và S5 nên làm trước.
2. Ai giữ danh sách profile phụ và cặp review? Lưu ở đâu?
3. Duyệt CI và CODEOWNERS?
4. Trace ngoài Git: có hay không?
5. Repo chính: `linhlban150612` hay `linh116365`?
