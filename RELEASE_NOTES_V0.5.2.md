# MXH Publisher v0.5.2

- Nhận diện thêm các cookie xác thực TikTok hiện hành; khi đã kết nối, nút kiểm
  tra mở thẳng TikTok Studio thay vì quay lại trang đăng nhập.
- TikTok tự tải video, điền caption, đặt ngày/giờ và bấm nút cuối. Nếu CAPTCHA,
  2FA, nút hoặc bằng chứng kết quả không chắc chắn, ứng dụng dừng và khóa chống
  gửi lại để tránh đăng trùng.
- Facebook tiếp tục đăng Fanpage bằng Meta Graph API nhưng không còn yêu cầu
  người dùng nhập lại giờ TikTok hoặc chờ TikTok hoàn tất; Page ID mặc định của
  dự án là 1099792776546051.
- Bỏ nút `Thiết lập` khỏi giao diện chính.
- Trạng thái `Nháp` hiển thị thành `Video đã sửa`; nút `Xóa bài/video` xóa được
  bài nháp cùng bản video đã sửa, nhưng không bao giờ xóa video nguồn.
