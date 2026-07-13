# MXH Publisher V0.5.3 — bản pilot Windows

Ứng dụng Windows hỗ trợ quản lý, duyệt và lên lịch cùng một video lên Facebook Fanpage và TikTok.

EXE được đóng gói dạng ứng dụng Windows GUI nên khi mở ứng dụng sẽ không tạo
hoặc để lại cửa sổ CMD.

Trước khi lưu bài, ứng dụng cắt đầu/cuối video, ghép khung PNG và xuất một bản
dùng chung 1080×1920, 30 fps, H.264/AAC cho cả Facebook và TikTok.

- Facebook: mở Meta Business Suite trong Chrome, tự chọn video đã biên tập và
  điền caption; người dùng kiểm tra rồi bấm Đăng/Lên lịch.
- Kết nối: Facebook và TikTok dùng cùng một tiến trình/hồ sơ Chrome bền vững;
  người dùng tự đăng nhập, ứng dụng gắn vào đúng cửa sổ đó và không đọc mật khẩu.
- TikTok: Playwright gắn vào Chrome đang mở, tự chọn video đã biên tập,
  điền caption, đặt lịch và bấm bước cuối khi đã nhận diện chắc chắn điều khiển.
  CAPTCHA/2FA hoặc giao diện không chắc chắn luôn làm tác vụ dừng.
- Dữ liệu: SQLite cục bộ; trạng thái, link và lỗi lưu riêng từng nền tảng.
- Bảo mật: luồng mặc định không cần Facebook Page token; không lưu mật khẩu,
  cookie hay token trong mã nguồn/database/log.

Đây là bản pilot để kiểm thử trên một Fanpage và một tài khoản TikTok thử. Chưa
phải bản production đã được ký mã hoặc xác nhận bằng tài khoản thật.

Các ranh giới an toàn quan trọng:

- Khóa Page ID và TikTok account theo từng bài trước khi đăng.
- Chống cùng một nội dung/lịch/tài khoản bị tạo thành hai bài cục bộ khác nhau.
- Băm lại toàn bộ video ngay trước khi giao cho TikTok hoặc Facebook.
- Chỉ cho TikTok upload tới đúng `https://www.tiktok.com/tiktokstudio/upload`.
- Sau khi file đã được đưa vào trình duyệt, tác vụ chuyển `Chờ xác nhận` và không
  upload lại khi bấm nút lần nữa.
- Không lưu ảnh màn hình login, CAPTCHA hoặc 2FA; ảnh TikTok khác tự hết hạn sau 7 ngày.

## Quy trình sử dụng

1. Bấm kết nối Facebook/TikTok và đăng nhập trong Chrome dùng chung của app.
2. Giữ cửa sổ Chrome này mở trong suốt lúc đăng Facebook/TikTok.
3. Chọn MP4 nguồn, nhập tiêu đề, caption, hashtag và giờ Việt Nam.
4. Bấm `Sửa video`; app dùng sẵn `nen.png`, cắt và lưu bản xuất vào `media/edited`.
5. Bấm `Đăng TikTok` hoặc `Đăng FB`; hai nút độc lập và có thể dùng theo bất kỳ
   thứ tự nào.
6. App tải video, điền caption, chọn giờ Việt Nam và tự bấm nút cuối khi nhận
   diện chắc chắn giao diện TikTok Studio. CAPTCHA/2FA hoặc giao diện lạ sẽ làm
   app dừng để người dùng xử lý, không tự gửi lại.
7. Nút `Đăng FB` mở đúng trình soạn Reel của Fanpage, tự chọn file và điền
   caption. Kiểm tra nội dung rồi bấm Đăng/Lên lịch ngay trong Chrome.
8. Mỗi nút khóa trạng thái sau khi đã đưa file lên để tránh upload trùng.

Lịch phải cách hiện tại ít nhất 60 phút để còn đủ thời gian thao tác và gửi lịch
an toàn. Mỗi nền tảng có trạng thái và khóa chống gửi trùng riêng.

## Biên tập và chuẩn video

- Mặc định bỏ 6,2 giây đầu và 4 giây cuối; có thể đổi riêng phần cuối.
- Video ngang được đặt ở giữa đúng tệp nền `assets/nen.png` 1080×1920 đã chốt.
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

## Kết nối Facebook và TikTok

Không cần Meta App hoặc Page access token. Bấm nút kết nối, tự đăng nhập trong
Chrome của ứng dụng và giữ Chrome mở. Page ID chỉ dùng để mở đúng trình soạn Reel
của Fanpage; TikTok dùng cùng hồ sơ Chrome đó.

## Kiểm thử

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Bộ test bao phủ:

- Migration/SQLite/approval hash.
- Trạng thái riêng Facebook–TikTok.
- Lease và phục hồi sau crash.
- TikTok chỉ click nút cuối sau khi nhận diện đủ video, caption, lịch và điều
  khiển tin cậy; kết quả không rõ bị khóa chống gửi lại.
- Facebook chọn đúng Fanpage/file, kiểm tra SHA-256 và khóa chống upload lặp.
- Luồng Facebook/TikTok độc lập và chống lặp thao tác theo từng nền tảng.

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
