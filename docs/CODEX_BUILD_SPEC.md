# Chỉ dẫn triển khai cho Codex — MXH Publisher v0.5.3

## Kết quả bắt buộc

Ứng dụng Windows cục bộ sửa một video rồi đưa cùng file đó lên Facebook Fanpage
và TikTok bằng một hồ sơ/một tiến trình Google Chrome riêng của ứng dụng.

## Quyết định kiến trúc

1. SQLite là nguồn trạng thái chuẩn; mỗi bài có delivery Facebook và TikTok riêng.
2. Video xuất được cắt mặc định 6,2 giây đầu, 4 giây cuối, đặt vào `assets/nen.png`
   1080×1920 và lưu trong `media/edited` trước khi đăng.
3. Băm SHA-256 lại ngay trước khi giao file cho mỗi nền tảng.
4. Nút kết nối mở Chrome với `browser_profile/chrome` và local DevTools port.
5. Playwright chỉ `connect_over_cdp` vào Chrome đang mở; không tạo context/profile
   thứ hai và không chạm hồ sơ Chrome cá nhân.
6. Facebook mở Meta Business Suite theo Page ID, chọn file và điền caption; người
   dùng kiểm tra rồi bấm nút cuối. Không yêu cầu Page access token.
7. TikTok tự chọn file, điền caption, đặt lịch và bấm nút cuối chỉ khi selector,
   URL và trạng thái đều chắc chắn.
8. CAPTCHA/2FA/login/giao diện lạ luôn dừng; không vượt xác minh, không chụp màn
   hình nhạy cảm.
9. Sau khi file đã được giao cho trình duyệt, delivery phải khóa ở
   `AWAITING_CONFIRMATION`, `SCHEDULED`, `PUBLISHED` hoặc trạng thái cần xử lý;
   không upload lại khi người dùng bấm lặp.
10. Không lưu mật khẩu, cookie hoặc token trong source, SQLite, log hay artifact.

## Nghiệm thu

- Toàn bộ pytest, Ruff, Mypy và compileall đạt.
- Windows PyInstaller build và smoke test đạt.
- Đăng nhập một lần trong Chrome dùng chung được tái sử dụng cho cả hai nền tảng.
- Facebook không truy cập Credential Manager trong luồng đăng mặc định.
- Đổi video sau khi khóa bị chặn bởi SHA-256.
- Không tạo upload thứ hai sau trạng thái chờ xác nhận/chưa rõ kết quả.
- Gói ZIP không chứa database, browser profile, token, log hoặc media người dùng.
