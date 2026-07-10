# Kiến trúc MXH Publisher V1

## Thành phần

- `ui`: giao diện Tkinter, không chứa logic nền tảng.
- `repository`: SQLite, migration, state transition, lease và attempt log.
- `services/media`: hash, ingest và ffprobe.
- `services/dry_run`: kiểm tra điều kiện trước khi chuẩn bị đăng.
- `services/orchestrator`: thực thi TikTok-first và Facebook scheduling.
- `publishers/facebook`: Meta Graph API v25.
- `publishers/tiktok`: TikTok Studio, headed Playwright, human-in-the-loop.
- `worker`: đối soát trạng thái có lease, không gọi publish theo giờ.

## Ranh giới an toàn

- UI chỉ gọi service; không viết SQLite trực tiếp.
- Publisher không tự đổi trạng thái database; orchestrator chịu trách nhiệm commit kết quả.
- Repository không gọi mạng.
- Mọi bí mật được cung cấp cho adapter tại thời điểm chạy, không được serialize.
- TikTok adapter trả về sau khi điền preview; không bấm nút cuối.

## Nguồn thời gian

- UI hiển thị `Asia/Ho_Chi_Minh`.
- Database lưu ISO-8601 UTC.
- Adapter nhận `datetime` timezone-aware.
- Scheduler phía nền tảng giữ lịch xuất bản; Task Scheduler chỉ đối soát.

