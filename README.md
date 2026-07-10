# MXH Publisher V1

Ứng dụng Windows hỗ trợ quản lý, duyệt và lên lịch cùng một video lên Facebook Fanpage và TikTok.

- Facebook: Meta Graph API v25.
- TikTok: Playwright mở TikTok Studio có giao diện, tự chọn video và điền caption; người dùng tự kiểm tra và bấm `Lên lịch`.
- Dữ liệu: SQLite cục bộ; trạng thái, link và lỗi lưu riêng từng nền tảng.
- Bảo mật: Page token lưu trong Windows Credential Manager; không lưu mật khẩu, cookie hay token trong mã nguồn/database/log.

Đây là MVP để kiểm thử trên một Fanpage và một tài khoản TikTok. Chưa phải bản cài đặt production đã được xác nhận bằng tài khoản thật.

## Quy trình sử dụng

1. Chọn MP4, nhập caption, hashtag và giờ Việt Nam.
2. Bấm `Lưu nháp`.
3. Kiểm tra lại nội dung rồi bấm `Duyệt + đặt lịch`; app sẽ lưu lại form hiện tại trước khi duyệt.
4. Chạy `Dry-run`.
5. Bấm `Chuẩn bị TikTok`.
6. Trong TikTok Studio, tự kiểm tra preview, chọn lịch và tự bấm nút cuối.
7. Quay lại app, bấm `Xác nhận TikTok + lịch FB`.
8. App mới upload và lên lịch Facebook bằng API.
9. Sau giờ đăng, ghi nhận link TikTok; worker đối soát trạng thái Facebook.

Không chọn bước 7 nếu TikTok chưa xuất hiện trong danh sách hẹn giờ.

## Chuẩn video V1

- MP4, H.264, AAC, có âm thanh.
- Dọc 9:16, tối thiểu 540×960; khuyến nghị 1080×1920.
- 24–60 fps; khuyến nghị 30 fps.
- 3–90 giây.

App chỉ kiểm tra và báo lỗi, không tự cắt hoặc chuyển mã.

## Cài môi trường phát triển trên Windows

Yêu cầu:

- Windows 10/11.
- Python 3.12.
- Microsoft Edge.
- `ffprobe.exe` trong `bin\ffprobe.exe`, hoặc FFmpeg có trong `PATH`.

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m mxh_publisher doctor
.\.venv\Scripts\python.exe -m mxh_publisher gui
```

TikTok dùng Edge đã cài trên Windows nên không cần tải trình duyệt Chromium riêng.

## Thiết lập Facebook

Ứng dụng cần một Meta App hợp lệ, Page ID và Page access token có các quyền cần thiết cho Fanpage. App Secret không được đưa vào EXE.

Cách lưu Page ID/token an toàn:

```powershell
.\.venv\Scripts\python.exe -m mxh_publisher configure-facebook --page-id PAGE_ID_CUA_THAY
```

Lệnh sẽ yêu cầu dán token bằng trường ẩn và lưu vào Windows Credential Manager. Có thể dùng cửa sổ `Thiết lập/kiểm tra` trong app; sau khi đổi Page ID cần khởi động lại.

Tham khảo chính thức: [Meta Reels Publishing API](https://developers.facebook.com/documentation/video-api/guides/reels-publishing).

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Bộ test bao phủ:

- Migration/SQLite/approval hash.
- Trạng thái riêng Facebook–TikTok.
- Lease và phục hồi sau crash.
- TikTok không có lệnh click nút đăng.
- Facebook start/upload/finish/status/permalink và unknown outcome.
- Luồng TikTok trước, Facebook sau và chống lặp thao tác.

## Build EXE

```powershell
.\scripts\build_windows.ps1
```

Kết quả nằm ở `dist\MXHPublisher\MXHPublisher.exe`. Sau khi thử nghiệm thật ổn định, có thể cài task chỉ để đối soát:

```powershell
.\scripts\install_verification_task.ps1
```

Task này không tự tạo bài đăng mới tại giờ chạy.

## Cấu trúc dữ liệu và chống đăng trùng

- Một `post` chứa nội dung chung.
- Mỗi post có hai `delivery`, một cho Facebook và một cho TikTok.
- Unique `(post_id, platform)`.
- Worker phải claim bằng lease trước khi đổi trạng thái.
- Nếu kết quả lệnh từ xa không rõ, delivery chuyển `UNKNOWN`; app không upload lại tự động.
- Chỉ ghi `PUBLISHED` khi có kết quả đã đối soát.

## Giới hạn V1

- Một Fanpage và một TikTok.
- Không Facebook cá nhân, Zalo, Telegram, analytics hoặc nhiều tài khoản.
- TikTok chưa tự lấy link một cách tin cậy; người dùng ghi nhận link sau khi đăng.
- Chưa kiểm thử live vì gói mã nguồn không chứa tài khoản/token của người dùng.
- Mọi CAPTCHA/2FA/login challenge phải được xử lý thủ công.

Chi tiết quyết định kỹ thuật nằm trong [docs/CODEX_BUILD_SPEC.md](docs/CODEX_BUILD_SPEC.md) và [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
