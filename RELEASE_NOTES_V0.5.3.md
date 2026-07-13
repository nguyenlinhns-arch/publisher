# MXH Publisher v0.5.3

Bản này đơn giản hóa hoàn toàn kết nối và đăng bài qua một Chrome dùng chung.

- Facebook không còn yêu cầu Page access token hoặc Windows Credential Manager.
- Facebook mở đúng trình soạn Reel của Fanpage, chọn file đã sửa và điền caption;
  người dùng kiểm tra rồi bấm Đăng/Lên lịch trong Chrome.
- TikTok không mở phiên Playwright thứ hai. App gắn vào chính cửa sổ Chrome đã
  đăng nhập nên phiên được dùng lại ổn định hơn.
- Facebook và TikTok dùng cùng hồ sơ Chrome riêng của ứng dụng; không đụng hồ sơ
  Chrome cá nhân.
- Giữ nguyên chốt SHA-256, trạng thái `Chờ xác nhận` và chống upload lặp.
- Giữ nguyên cắt 6,2 giây đầu, 4 giây cuối, nền xanh mặc định và file đã sửa.
- CAPTCHA/2FA luôn dừng để người dùng tự xử lý; ứng dụng không vượt xác minh.

Khi nâng cấp từ v0.5.2, nếu app báo Chrome cũ chưa bật kết nối nội bộ, hãy đóng
các cửa sổ Chrome do MXH Publisher mở, bấm Kết nối lại một lần và tiếp tục dùng
chính cửa sổ đó.
