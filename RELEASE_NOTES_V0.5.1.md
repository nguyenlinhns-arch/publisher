# MXH Publisher v0.5.1

- Kết nối Facebook và TikTok bằng Google Chrome thường, dùng chung hồ sơ đã lưu;
  trang đăng nhập không còn bị Playwright gắn trình gỡ lỗi.
- Dùng chính `nen.png` 1080×1920 do người dùng cung cấp làm khung nền mặc định.
- Video được cắt 6,2 giây đầu và 4 giây cuối, ghép khung, rồi lưu thành tệp riêng
  trong thư mục `media/edited` trước khi đăng.
- Nút xóa chỉ xóa bản video do ứng dụng xuất và chặn xóa khi còn tác vụ đang chờ,
  đang tải hoặc chưa rõ kết quả. Video gốc không bị xóa.
- Đăng TikTok không còn bắt buộc phải cấu hình Facebook Page ID hoặc nhập tài
  khoản TikTok thủ công; hồ sơ Chrome đã đăng nhập là danh tính đích mặc định.
