# MXH Publisher V0.4.4 — bản pilot Windows

Ứng dụng Windows hỗ trợ quản lý, duyệt và lên lịch cùng một video lên Facebook Fanpage và TikTok.

EXE được đóng gói dạng ứng dụng Windows GUI nên khi mở ứng dụng sẽ không tạo
hoặc để lại cửa sổ CMD.

Trước khi lưu bài, ứng dụng cắt đầu/cuối video, ghép khung PNG và xuất một bản
dùng chung 1080×1920, 30 fps, H.264/AAC cho cả Facebook và TikTok.

- Facebook: Meta Graph API v25.
- Kết nối: Facebook và TikTok mở trong cùng một hồ sơ Chrome bền vững; người dùng
  tự đăng nhập, ứng dụng dùng lại cookie/phiên đó và không đọc mật khẩu.
- TikTok: Playwright mở TikTok Studio có giao diện, tự chọn video đã biên tập và
  điền caption; người dùng tự kiểm tra và bấm `Lên lịch`.
- Dữ liệu: SQLite cục bộ; trạng thái, link và lỗi lưu riêng từng nền tảng.
- Bảo mật: Page token lưu trong Windows Credential Manager; không lưu mật khẩu, cookie hay token trong mã nguồn/database/log.

Đây là bản pilot để kiểm thử trên một Fanpage và một tài khoản TikTok thử. Chưa
phải bản production đã được ký mã hoặc xác nhận bằng tài khoản thật.

Các ranh giới an toàn quan trọng:

- Khóa Page ID và TikTok account theo từng bài trước khi đăng.
- Chống cùng một nội dung/lịch/tài khoản bị tạo thành hai bài cục bộ khác nhau.
- Băm lại toàn bộ video ngay trước khi giao cho TikTok hoặc Facebook.
- Chỉ cho TikTok upload tới đúng `https://www.tiktok.com/tiktokstudio/upload`.
- Kết quả Facebook chưa rõ được đối soát chỉ-đọc theo `video_id`, không upload lại.
- Không lưu ảnh màn hình login, CAPTCHA hoặc 2FA; ảnh TikTok khác tự hết hạn sau 7 ngày.

## Quy trình sử dụng

1. Chọn MP4 nguồn, khung PNG, số giây cắt đầu/cuối; nhập caption, hashtag và giờ Việt Nam.
2. Bấm `Lưu nháp`.
3. Kiểm tra lại nội dung rồi bấm `Duyệt nội dung + khóa lịch`; app khóa Page,
   TikTok account và lịch cho bài đó.
4. Chạy `Dry-run`.
5. Bấm `Chuẩn bị TikTok`.
6. Trong TikTok Studio, tự kiểm tra preview, chọn đúng giờ Việt Nam app hiển thị
   và tự bấm nút cuối.
7. Quay lại app, bấm `Xác nhận TikTok + lịch FB` rồi nhập lại chính xác giờ đã
   thấy trong danh sách hẹn giờ TikTok.
8. App mới upload và lên lịch Facebook bằng API.
9. Sau giờ đăng, ghi nhận link TikTok; worker đối soát trạng thái Facebook.

Không xác nhận bước 7 nếu sai TikTok account, sai giờ hoặc video chưa xuất hiện
trong danh sách hẹn giờ. Lịch phải cách hiện tại ít nhất 60 phút để còn đủ thời
gian thao tác và gửi lịch Facebook an toàn.

## Biên tập và chuẩn video

- Mặc định bỏ 6,2 giây đầu và 4 giây cuối; có thể đổi riêng phần cuối.
- Video ngang được đặt ở giữa khung xanh 1080×1920 theo đúng mẫu đã chốt.
- Tiêu đề bài được viết hoa, tự chia tối đa ba dòng, chữ trắng viền đen; có thể
  dùng dấu `|` trong tiêu đề để chủ động ngắt dòng.
- App xuất bản upload bất biến bằng FFmpeg rồi mới chạy kiểm tra chuẩn.

- MP4, H.264, AAC, có âm thanh.
- Dọc 9:16, tối thiểu 540×960; khuyến nghị 1080×1920.
- 24–60 fps; khuyến nghị 30 fps.
- Không giới hạn thời lượng tối đa sau khi cắt; ứng dụng giữ nguyên toàn bộ phần
  còn lại sau khi bỏ 6,2 giây đầu và 4 giây cuối.

## Cài môi trường phát triển trên Windows

Yêu cầu:

- Windows 10/11.
- Python 3.12.
- Google Chrome.
- `ffmpeg.exe` và `ffprobe.exe` trong thư mục `bin`, hoặc FFmpeg có trong `PATH`.

PowerShell:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m mxh_publisher doctor
.\.venv\Scripts\python.exe -m mxh_publisher gui
```

TikTok dùng Google Chrome đã cài trên Windows nên không cần tải trình duyệt Chromium riêng.

## Thiết lập Facebook

Ứng dụng cần một Meta App hợp lệ, Page ID và Page access token có các quyền cần
thiết cho Fanpage. App Secret không được đưa vào EXE. Xem checklist tại
[docs/FACEBOOK_SETUP.md](docs/FACEBOOK_SETUP.md).

Cách lưu Page ID/token an toàn:

```powershell
.\.venv\Scripts\python.exe -m mxh_publisher configure-facebook --page-id PAGE_ID_CUA_THAY
```

Lệnh sẽ yêu cầu dán token bằng trường ẩn và lưu vào Windows Credential Manager.
Trong cửa sổ `Thiết lập/kiểm tra`, nhập thêm TikTok `@username`; sau khi đổi tài
khoản phải khởi động lại và duyệt một bài mới.

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
.\scripts\fetch_ffprobe.ps1
.\scripts\build_windows.ps1
.\scripts\smoke_windows.ps1
.\scripts\package_windows.ps1
```

Kết quả portable nằm trong `release\` dưới dạng ZIP kèm SHA-256. Phải giữ nguyên
toàn bộ thư mục `MXHPublisher`, không chép riêng EXE. Xem
[docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md).

Sau khi thử nghiệm thật ổn định, có thể cài task chỉ để đối soát Facebook:

```powershell
.\scripts\install_verification_task.ps1
```

Task này không tự tạo bài đăng mới tại giờ chạy.

## Cấu trúc dữ liệu và chống đăng trùng

- Một `post` chứa nội dung chung.
- Mỗi post có hai `delivery`, một cho Facebook và một cho TikTok.
- Unique `(post_id, platform)`.
- Unique `idempotency_key` xuyên các bài đang hoạt động.
- Worker phải claim bằng lease trước khi đổi trạng thái.
- Nếu kết quả lệnh từ xa không rõ, delivery chuyển `UNKNOWN`; app không upload lại tự động.
- `UNKNOWN` có remote ID chỉ được worker hỏi trạng thái, không gọi start/upload/finish.
- Chỉ ghi `PUBLISHED` khi có kết quả đã đối soát.

## Giới hạn V1

- Một Fanpage và một TikTok.
- Không Facebook cá nhân, Zalo, Telegram, analytics hoặc nhiều tài khoản.
- TikTok chưa tự lấy link một cách tin cậy; người dùng ghi nhận link sau khi đăng.
- Chưa kiểm thử live vì gói mã nguồn không chứa tài khoản/token của người dùng.
- Mọi CAPTCHA/2FA/login challenge phải được xử lý thủ công.
- Chưa ký mã nên Windows SmartScreen có thể cảnh báo.

Trước khi dùng tài khoản chính, hoàn thành
[docs/PILOT_ACCEPTANCE.md](docs/PILOT_ACCEPTANCE.md). Cách xử lý sự cố nằm trong
[docs/RECOVERY_RUNBOOK.md](docs/RECOVERY_RUNBOOK.md); dữ liệu/gỡ cài đặt nằm trong
[docs/BACKUP_PRIVACY_UNINSTALL.md](docs/BACKUP_PRIVACY_UNINSTALL.md).

Chi tiết quyết định kỹ thuật nằm trong
[docs/CODEX_BUILD_SPEC.md](docs/CODEX_BUILD_SPEC.md) và
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).
