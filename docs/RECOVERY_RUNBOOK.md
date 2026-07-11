# Xử lý sự cố và tránh đăng trùng

## `UNKNOWN`

- Không bấm thử lại và không tạo bài mới.
- Nếu Facebook đã có `video_id`, worker chỉ hỏi trạng thái sau 15 phút; không gọi
  start/upload/finish.
- Mở Fanpage/TikTok Studio và tìm theo video, caption, account và giờ.
- Chỉ dùng `Ghi nhận link đã đăng` khi đã mở đúng bài và có ID/link thật.

## `NEEDS_ACTION`

- Đọc lỗi trong giao diện/log.
- Với 401/403: kiểm tra Page, token, quyền; không upload lại.
- Với CAPTCHA/2FA/login: xử lý trực tiếp trong Edge.
- Với account mismatch: đổi lại đúng account đã khóa hoặc tạo bài mới và duyệt
  lại; không đổi delivery đã có remote evidence.

## TikTok đã hẹn nhưng Facebook chưa hẹn

- Không tạo TikTok lần hai.
- Kiểm tra khoảng thời gian còn lại và cấu hình Facebook.
- Nếu không còn đủ 60 phút, xử lý lịch TikTok thủ công rồi tạo một bài/lịch mới;
  ghi lại quyết định để tránh hai nền tảng lệch giờ.

## Chỉ dùng `Thử lại sau kiểm tra` khi

Đã xác minh chắc chắn trên đúng account rằng không có draft, upload, lịch hoặc
bài đăng từ attempt trước. Nếu có bất kỳ remote ID nào, repository sẽ chặn
requeue.
