# MXH Publisher v0.4.0

- Thêm bước cắt video: mặc định bỏ 6,2 giây đầu và 6,2 giây cuối; người dùng có
  thể điều chỉnh riêng phần cuối.
- Thêm chọn khung PNG và xuất video dọc 1080×1920, 30 fps, H.264/AAC bằng
  FFmpeg trước khi kiểm tra và đăng.
- Video nguồn ngang hoặc chưa đúng chuẩn được biên tập trước, không còn bị chặn
  bởi kiểm tra chuẩn đầu vào.
- Facebook và TikTok dùng chung một hồ sơ Edge; TikTok mở trong cùng phiên đã
  dùng đăng nhập Facebook và lưu trạng thái đăng nhập để tái sử dụng.
- Khắc phục lỗi khởi tạo Playwright Sync API lần thứ hai khi kết nối TikTok.
- Đóng gói cả `ffmpeg.exe` và `ffprobe.exe` trong bản Windows.

Ứng dụng vẫn không bấm nút Đăng/Lên lịch cuối cùng trên TikTok và không xử lý
thay CAPTCHA hoặc 2FA.
