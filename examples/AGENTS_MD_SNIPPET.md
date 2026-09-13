# Snippet cho `AGENTS.md` của repo

> `AGENTS.md` là contract chung mà cả Lead và Peer đọc tại repo đích. Chỉ giữ điều khoản có
> constraint thật; mỗi điều khoản nên có lý do tái hiện được và điều kiện để xem xét lại.

## Product boundary

- application/domain core:
- adapter/transport boundary (chỉ dịch protocol, không sở hữu workflow hoặc policy):
- execution/runtime boundary:
- generated/runtime data phải nằm ngoài Git:

## Canonical documentation

- product intent / roadmap:
- architecture / security:
- development / verification:
- operations:

Chỉ thêm tài liệu mới khi nó không thuộc tài liệu chuẩn nào và không thể đặt cạnh code mà nó mô tả.

## Contract boundary

- seam **đã chốt** (cứ dùng, không hỏi lại):
- seam **phải quyết trước** khi có test đi qua; chưa quyết thì báo `BLOCKED`:

## Authority

- được tự quyết thêm:
- luôn phải hỏi Human:
- ranh giới môi trường (port, DB, network, dữ liệu):
- artifact được phép commit / phải giữ ngoài Git:

## Verification

- lệnh cho thay đổi thường:
- lệnh trước khi Lead accept:
- bằng chứng cho UX hoặc chất lượng chủ quan:

## Ví dụ điều khoản có trigger review

```md
- Mọi thay đổi chạm `store/migrations/` phải có review độc lập.
  Lý do: migration từng làm mất dữ liệu dev mà unit test không phát hiện.
  Trigger review: gỡ khi CI chạy migration trên bản sao dữ liệu đại diện.
```

## Rủi ro riêng của repo

- quyết định khó đảo ngược:
- external side effect:

Không sao chép persona hoặc schema handoff của seat vào đây. Chỉ bổ sung constraint của repo;
với client không nạp prompt seat, thêm hướng dẫn cần thiết theo contract riêng của client đó.
