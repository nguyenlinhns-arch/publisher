# Chỉ dẫn triển khai cho Codex — MXH Publisher V1

## 1. Kết quả cần đạt

Xây một ứng dụng Windows cục bộ để quản lý, duyệt và lên lịch cùng một video lên:

- Facebook Fanpage qua Meta Graph API.
- TikTok qua TikTok Studio web và Playwright có người xác nhận.

Ứng dụng không đăng Facebook cá nhân, không vượt CAPTCHA/2FA, không lưu mật khẩu, không bấm nút đăng/lên lịch cuối cùng trên TikTok và không tự xóa video.

## 2. Quyết định kiến trúc bắt buộc

1. SQLite là nguồn dữ liệu chuẩn duy nhất; Excel/Google Sheets chỉ là định dạng nhập/xuất về sau.
2. Mỗi bài có hai `delivery`: `facebook` và `tiktok`; trạng thái và lỗi không dùng chung.
3. TikTok phải được người dùng xác nhận đã lên lịch trước khi ứng dụng gửi lịch Facebook.
4. Không chờ TikTok xuất bản thật mới hẹn Facebook; hai nền tảng phải có cùng `scheduled_at_utc`.
5. Facebook dùng Graph API có version cố định; Playwright không được dùng để bấm đăng Facebook.
6. Playwright TikTok chạy headed với persistent profile ngoài repo; dừng tại preview.
7. `publish_id`, `video_id` hoặc phản hồi nhận tác vụ không đồng nghĩa `PUBLISHED`.
8. Mất kết nối tại thời điểm kết quả không chắc chắn phải chuyển `UNKNOWN`/`NEEDS_ACTION`, không tự tạo tác vụ mới.
9. Video/caption/hashtag thay đổi sau khi duyệt phải tự hủy duyệt.
10. Không lưu token/cookie/session trong source, SQLite, log, ảnh chụp hay gói chẩn đoán.

## 3. Luồng nghiệp vụ

1. Nhập video và sao chép vào thư mục media do app quản lý.
2. Tính SHA-256, đọc thông số bằng ffprobe.
3. Nhập caption, hashtag và giờ Việt Nam; lưu UTC trong SQLite.
4. Duyệt nội dung: tạo `content_hash` từ video fingerprint + caption + hashtag.
   Khi khóa lịch, tạo `idempotency_key` từ platform + account + SHA-256 video +
   caption/hashtag + lịch UTC; cả hai phải còn khớp trước remote mutation.
5. Dry-run: duyệt, hash, video, caption, lịch, Page ID/token và môi trường TikTok.
6. Chuẩn bị TikTok: upload, điền caption, chụp ảnh; trả `AWAITING_CONFIRMATION`.
7. Người dùng tự chọn lịch và bấm nút cuối trên TikTok Studio.
8. Người dùng xác nhận trong app; app ghi TikTok `SCHEDULED` rồi mới gửi Facebook `SCHEDULED`.
9. Worker chỉ kiểm tra/đối soát; không phụ thuộc máy tính để gọi publish đúng giây.
10. Chỉ `PUBLISHED` khi có tín hiệu hoàn tất và, khi nền tảng cung cấp, permalink hợp lệ.

## 4. Chuẩn video V1

- MP4, H.264, AAC.
- Dọc 9:16; tối thiểu 540×960, khuyến nghị 1080×1920.
- 24–60 fps, khuyến nghị 30 fps.
- Không đặt giới hạn thời lượng tối đa sau khi cắt.
- Có âm thanh.
- Không tự cắt một giây, không tự chuyển mã trong V1.

## 5. Trạng thái

Post: `DRAFT`, `APPROVED`, `READY`, `PARTIAL`, `COMPLETED`, `NEEDS_ACTION`, `CANCELLED`.

Delivery: `PENDING`, `PREPARING`, `AWAITING_CONFIRMATION`, `SCHEDULED`, `PROCESSING`, `PUBLISHED`, `RETRY_WAIT`, `UNKNOWN`, `NEEDS_ACTION`, `FAILED`, `CANCELLED`.

Mọi chuyển trạng thái phải được Repository kiểm tra. Không cho chuyển từ trạng thái cuối về trạng thái đang xử lý nếu không có thao tác khôi phục rõ ràng.

## 6. Chống đăng trùng

- Unique `(post_id, platform)`.
- Unique `idempotency_key` cho mọi delivery chưa hủy, ngăn hai local post giống
  nhau tạo hai lịch trên cùng account.
- Worker claim delivery trong transaction với lease có hạn.
- Lưu remote ID ngay khi nền tảng cấp.
- Khi remote ID đã có, phục hồi phải query trạng thái trước khi tạo upload mới.
- `UNKNOWN` có remote ID được claim riêng cho đối soát chỉ-đọc; không được gọi
  lại start/upload/finish.
- Chỉ retry tự động lỗi mạng trước upload, HTTP 429 và 5xx đã xác định an toàn.
- 401/403, lỗi quyền, nội dung, CAPTCHA/2FA hoặc UI lạ chuyển `NEEDS_ACTION`.
- Log mọi attempt nhưng phải làm sạch token, Authorization và URL nhạy cảm.

## 7. Bảo mật

- Facebook Page token: Windows Credential Manager qua `keyring`.
- App Secret không nằm trong EXE.
- TikTok login do persistent browser profile quản lý tại `%LOCALAPPDATA%/MXHPublisher`.
- `.gitignore` chặn data, log, screenshot, database, profile và secret.
- Gói chẩn đoán không chứa database thô, browser profile hoặc token.

## 8. Điều kiện nghiệm thu V1

- Tất cả test cục bộ qua.
- Tạo, sửa, duyệt, dry-run được một bài.
- Sửa nội dung sau duyệt làm mất duyệt.
- Không tạo được delivery trùng.
- TikTok adapter không gọi click lên nút submit/schedule/publish cuối.
- Facebook adapter được mock đủ start → upload → finish → status.
- Mất mạng sau upload trả `UNKNOWN`, không tự gửi lại.
- Có `doctor` kiểm tra database, ffprobe, thư mục, keyring và Playwright.
- Không có token, cookie hoặc mật khẩu mẫu trong repo.
- Có hướng dẫn thử nghiệm bằng Page/TikTok thử trước tài khoản chính.

## 9. Những việc không làm trong V1

- Zalo Video.
- Facebook cá nhân.
- Nhiều tài khoản.
- Analytics và trả lời bình luận/tin nhắn.
- Telegram điều khiển.
- Tự cập nhật.
- Tự giải CAPTCHA hoặc né xác minh.
- TikTok Direct Post API khi ứng dụng vẫn chỉ dùng nội bộ.
