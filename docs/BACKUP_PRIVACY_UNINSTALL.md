# Sao lưu, riêng tư và gỡ ứng dụng

Dữ liệu nằm tại `%LOCALAPPDATA%\MXHPublisher`:

- `publisher.sqlite3`: bài, delivery và audit attempt.
- `media`: bản video app quản lý.
- `logs`: log đã che token.
- `screenshots`: ảnh TikTok không nhạy cảm; ảnh quá 7 ngày tự được dọn khi app
  chụp ảnh mới.
- `browser_profile`: phiên Edge/TikTok, có dữ liệu đăng nhập nhạy cảm.

## Sao lưu

Đóng app và Task Scheduler, sau đó sao chép toàn bộ thư mục trên vào ổ mã hóa.
Không đưa backup lên GitHub hoặc dịch vụ chia sẻ công khai.

## Gỡ

1. Chạy `tools\uninstall_verification_task.ps1` nếu đã cài task.
2. Thu hồi/xóa Facebook Page token trong Windows Credential Manager.
3. Xóa thư mục ứng dụng portable.
4. Chỉ khi không cần lịch sử/audit nữa mới xóa
   `%LOCALAPPDATA%\MXHPublisher`; thao tác này xóa cả database, media và phiên
   TikTok.

App không tự xóa video đã nhập. Theo dõi dung lượng `media` và chỉ dọn khi đã có
backup và không còn bài/attempt cần đối soát.
