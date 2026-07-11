# MXH Publisher V0.2.0 — Windows pilot

Ngày phát hành kỹ thuật: 11/07/2026.

## Thay đổi chính

- Thêm GitHub Actions build thật trên Windows 2025/Python 3.12, smoke test bản
  PyInstaller `onedir`, đóng gói ZIP và SHA-256.
- Bundled `ffprobe.exe` 8.1.2 từ Gyan sau khi kiểm tra SHA-256 cố định; kèm
  attribution và giấy phép trong gói.
- Khóa URL TikTok Studio trước và ngay sát thao tác chọn video; bỏ fallback
  Chromium không được đóng gói.
- Không lưu ảnh login/CAPTCHA/2FA; tự xóa ảnh TikTok quá 7 ngày.
- Băm lại video trước cả TikTok và Facebook.
- Khóa Facebook Page ID và TikTok account theo delivery; đổi tài khoản sẽ chặn
  bài đã duyệt.
- Thêm idempotency key ngăn hai local post giống hệt nhau tạo hai lịch từ xa.
- `UNKNOWN` có remote ID được đối soát chỉ-đọc sau 15 phút, không upload lại.
- Manual resolution bị chặn khi worker còn lease, sai trạng thái hoặc URL không
  thuộc nền tảng.
- UI hiển thị TikTok account và giờ Việt Nam; người dùng phải nhập lại đúng giờ
  trước khi app gửi lịch Facebook.
- Tăng khoảng đệm vận hành tối thiểu lên 60 phút và chạy lại dry-run ngay trước
  Facebook.
- Doctor có chế độ `--system-only`, thực chạy ffprobe và Playwright driver.
- Schema SQLite nâng lên phiên bản 3; migration tự động khi mở ứng dụng.

## Xác minh

- 78 kiểm thử tự động cục bộ đạt.
- Ruff, Mypy và Compileall đạt.
- Bản Windows phải đạt workflow `Windows build` và smoke test trước khi dùng.

## Giới hạn bắt buộc

- Bản pilot chưa ký mã; SmartScreen có thể cảnh báo.
- Chưa thực hiện end-to-end bằng Page/TikTok thật vì không có token hoặc phiên
  đăng nhập của chủ tài khoản trong môi trường build.
- TikTok vẫn là human-in-the-loop: ứng dụng không bấm nút Post/Schedule cuối.
- Chỉ chuyển sang tài khoản chính sau khi hoàn thành `docs/PILOT_ACCEPTANCE.md`.
