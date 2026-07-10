# MXH Publisher V0.1.0 — MVP kỹ thuật

Ngày đóng gói: 10/07/2026.

## Đã hoàn thành

- Giao diện Windows Tkinter quản lý bài, video, caption, hashtag và lịch.
- SQLite WAL, migration, trạng thái riêng từng nền tảng và attempt log.
- Approval/content hash; thay video hoặc nội dung sẽ mất duyệt.
- Kiểm tra video bằng ffprobe và dry-run.
- TikTok Studio qua Playwright headed, persistent profile ngoài repo, không bấm nút cuối.
- Facebook Reels Graph API v25: start, upload/resume, finish, schedule, status và permalink.
- TikTok-first gate: Facebook chỉ chạy sau xác nhận TikTok đã lên lịch.
- Lease và `UNKNOWN` để tránh đăng trùng khi worker/crash/mất phản hồi.
- Windows Credential Manager cho Page token.
- Worker/Task Scheduler chỉ đối soát Facebook, không tạo bài mới đúng giờ.

## Xác minh tự động

- 49 test đạt, gồm kiểm thử giữ Facebook `video_id` khi kết quả chưa rõ, heartbeat lease và chặn mọi đường requeue/lên lịch gây trùng.
- Ruff lint đạt.
- Mypy đạt trên toàn bộ source.
- Compileall đạt.
- Doctor đạt 0 lỗi chặn trong môi trường phát triển; cảnh báo đúng rằng môi trường kiểm tra không phải Windows.

## Chưa xác minh

- Chưa đăng thật do không nhận Page ID/token hoặc phiên TikTok của người dùng.
- Chưa chạy PyInstaller trực tiếp trên Windows.
- Selector TikTok cần kiểm tra trên giao diện tài khoản thật trước production.
- Meta App/quyền/Page token phải được cấu hình riêng và kiểm tra bằng Fanpage thử.

## Điều kiện trước khi dùng tài khoản chính

1. Build trên Windows và chạy `doctor`.
2. Dùng một video thử không nhạy cảm.
3. Kiểm thử TikTok ở chế độ lịch riêng, xác nhận không có auto-click.
4. Kiểm thử Facebook trên Fanpage thử, đối soát link.
5. Thử ngắt mạng ở ba thời điểm: trước upload, trong upload, sau finish.
6. Chỉ chuyển sang Fanpage/TikTok chính sau khi log và trạng thái đều đúng.
