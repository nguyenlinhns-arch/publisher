# MXH Publisher v0.5.4

Bản sửa khẩn cấp cho lỗi đăng nhập/đăng bài của v0.5.3.

- Nút Kết nối TikTok chỉ mở Chrome để người dùng đăng nhập; tuyệt đối chưa gắn
  Playwright trong lúc trang đăng nhập/CAPTCHA/2FA đang hiển thị.
- Facebook và TikTok dùng đúng một Playwright/CDP session sau khi đăng nhập,
  không còn lỗi `Sync API inside the asyncio loop` do tạo phiên thứ hai.
- Facebook và TikTok vẫn dùng cùng hồ sơ Chrome riêng của ứng dụng.
- Lỗi khởi động trình duyệt trước upload chuyển về trạng thái có thể thử lại.
- Tự mở khóa tác vụ `Cần xử lý` do lỗi trình duyệt hoặc đăng nhập trước upload từ
  v0.5.3, miễn là chưa có dấu vết file/bài trên nền tảng.
- Không upload lại khi đã có dấu vết từ Facebook/TikTok; giữ nguyên chốt chống
  đăng trùng, SHA-256 và dừng CAPTCHA/2FA.

Sau khi cài v0.5.4, đóng Chrome do v0.5.3 mở, chạy app, bấm Kết nối TikTok, đăng
nhập hoàn tất và giữ Chrome mở. Chỉ sau đó bấm Đăng TikTok hoặc Đăng FB.
