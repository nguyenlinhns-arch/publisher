# Kiến trúc MXH Publisher V1

## Thành phần

- `ui`: giao diện Tkinter, không chứa logic nền tảng.
- `repository`: SQLite, migration, state transition, lease và attempt log.
- `services/media`: hash, ingest và ffprobe.
- `services/dry_run`: kiểm tra điều kiện trước khi chuẩn bị đăng.
- `services/orchestrator`: điều phối và khóa chống upload lặp theo nền tảng.
- `publishers/facebook_browser`: Meta Business Suite qua Chrome dùng chung.
- `publishers/tiktok`: TikTok Studio qua cùng Chrome, tự động có chốt an toàn.
- `worker`: đối soát trạng thái có lease, không gọi publish theo giờ.

## Ranh giới an toàn

- UI chỉ gọi service; không viết SQLite trực tiếp.
- Publisher không tự đổi trạng thái database; orchestrator chịu trách nhiệm commit kết quả.
- Repository không gọi mạng.
- `content_hash` khóa media/nội dung; `idempotency_key` khóa thêm platform,
  account và lịch UTC. Mutation chỉ chạy khi cả hai còn khớp.
- Mọi bí mật được cung cấp cho adapter tại thời điểm chạy, không được serialize.
- Facebook dừng ở preview để người dùng kiểm tra nút cuối.
- TikTok chỉ bấm nút cuối sau khi nhận diện chắc chắn đủ điều khiển; CAPTCHA/2FA
  hoặc giao diện lạ luôn dừng.

## Nguồn thời gian

- UI hiển thị `Asia/Ho_Chi_Minh`.
- Database lưu ISO-8601 UTC.
- Adapter nhận `datetime` timezone-aware.
- Scheduler phía nền tảng giữ lịch xuất bản; Task Scheduler chỉ đối soát.
- Khoảng đệm vận hành tối thiểu là 60 phút; dry-run được chạy lại ngay trước
  khi gửi Facebook.
