# Workspace Protocol

> Policy điều phối riêng của một repository. Lead đọc trước khi route task; Peer không cần
> đọc file này. Giữ policy theo risk của repo, không ghi task-specific file list hoặc model ID
> có thể lỗi thời. Đây là policy vận hành, không mặc định là product artifact phải commit: nếu
> repository cấm process document thì giữ file local/ignored hoặc ở nơi Human quản lý.

## Status

- owner: Human/project owner
- version: 1
- last reviewed: YYYY-MM-DD
- applies to: `<repository-root>`
- readers: Lead; reviewer governance chỉ khi được giao audit/update

## Project characteristics

- criticality:
- dominant risks:
- expensive-to-reverse decisions:
- external side effects:
- canonical docs (nếu có):
- repository artifacts bị cấm commit:

## Authority

Tham chiếu § Authority trong `AGENTS.md`; chỉ ghi quyết định điều phối bổ sung tại đây:

- topology/reviewer cần Human duyệt:

## Task classes

### Tiny / bounded

- Một Engineer, hoặc Lead tự làm nếu tightly coupled.
- Targeted verification; independent review là tùy chọn.

### Cross-module / lifecycle-sensitive

- Architect read-only trước implementation khi foundation/ownership chưa rõ.
- Một Engineer giữ một moving write scope; writer song song dùng worktree riêng.
- Reviewer độc lập falsify đúng stable candidate khi risk yêu cầu.

### Architecture lock-in

- Các lượt tư vấn độc lập nhận brief trung lập và nêu reversal conditions.
- Lead chốt một project verdict; Human quyết trade-off product/cost khó đảo ngược.

## Ownership and workspace

- vị trí/quy ước worktree riêng của repo:
- integration owner:

## Routing

- Discover provider/model đang khả dụng, không hard-code ID dễ lỗi thời.
- Dùng model/effort Human đã chọn. Task risk chỉ là lý do đề xuất thay đổi; chỉ đổi sau khi
  Human cho phép, discovery không tự cấp quyền đổi.
- Paseo quản lý session, parentage, lifecycle và workspace; protocol này quản lý chiến thuật.

## Verification

Lệnh và proof chuẩn nằm trong § Verification của `AGENTS.md`; không sao chép chúng ở đây.

- task class → nhóm check bắt buộc/tùy chọn trong `AGENTS.md`:
- independent-review triggers bổ sung (ngoài gate mặc định của Lead):
- điều phối lane test/port/DB giữa các agent:

## Project-specific anti-patterns

- signal:
- evidence required:
- allowed response:
- điều kiện xem xét lại policy:

## Evolution

- Chỉ đổi policy khi có causal evidence hoặc architecture/risk của repo thay đổi.
- Human duyệt thay đổi authority quan trọng; giữ version history và ngày review.
- Không sinh evidence folder, review packet hay status ledger trong Git chỉ để phục vụ orchestration.
