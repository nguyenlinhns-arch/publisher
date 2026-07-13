# Cài và chạy MXH Publisher trên Windows

## Yêu cầu

- Windows 10 hoặc Windows 11, máy x64.
- Google Chrome bản ổn định.
- Tài khoản Facebook Fanpage và TikTok do người dùng tự đăng nhập/cấu hình.

Gói thử nghiệm hiện chưa ký mã. Windows SmartScreen có thể cảnh báo khi mở lần
đầu. Chỉ sử dụng ZIP tải từ GitHub Actions của repository chính thức và luôn
đối chiếu SHA-256 trước khi chạy.

## Cài từ artifact GitHub Actions

1. Mở workflow `Windows build` đã chạy thành công.
2. Tải artifact có tên `MXHPublisher-Windows-x64-<commit>`.
3. Giải nén artifact; bên trong có một ZIP phát hành và tệp `.sha256`.
4. Mở PowerShell tại thư mục đó và kiểm tra:

   ```powershell
   Get-FileHash .\MXHPublisher-0.4.3-Windows-x64.zip -Algorithm SHA256
   Get-Content .\MXHPublisher-0.4.3-Windows-x64.zip.sha256
   ```

5. Hai giá trị phải giống nhau. Sau đó giải nén ZIP đến một thư mục cố định.
6. Giữ nguyên toàn bộ thư mục `MXHPublisher`; không chép riêng tệp EXE.

Ứng dụng dùng PyInstaller `onedir`. Thư mục `_internal` chứa Python, Tcl/Tk,
Playwright driver, múi giờ, `ffmpeg.exe` và `ffprobe.exe`; thiếu bất kỳ phần nào ứng dụng có
thể không chạy hoặc không kiểm tra được video.

## Kiểm tra hệ thống

Từ PowerShell trong thư mục ứng dụng:

```powershell
.\MXHPublisher.exe doctor --system-only
```

Nếu đang dùng bản cũ chưa có tùy chọn `--system-only`, chạy:

```powershell
.\MXHPublisher.exe doctor
```

Kết quả phải có 0 lỗi chặn. Kiểm tra này không cần Page token Facebook và không
đăng nội dung lên bất kỳ nền tảng nào.

## Cấu hình Facebook

```powershell
.\MXHPublisher.exe configure-facebook --page-id PAGE_ID_CUA_THAY
```

Page access token được nhập ẩn và lưu trong Windows Credential Manager. Không
đưa token vào file cấu hình, ảnh chụp, issue GitHub hoặc log.

## Mở ứng dụng

```powershell
.\MXHPublisher.exe gui
```

Facebook và TikTok dùng chung một hồ sơ Chrome của ứng dụng. Đăng nhập Facebook
trước, sau đó bấm kết nối TikTok; TikTok mở trong cùng phiên Chrome và phiên đăng
nhập được dùng lại ở những lần sau.

Lần đầu chuẩn bị TikTok, đăng nhập trực tiếp trong cửa sổ Chrome do ứng dụng mở.
Ứng dụng không lưu mật khẩu TikTok. CAPTCHA và 2FA luôn do người dùng xử lý.

Dữ liệu cục bộ nằm tại `%LOCALAPPDATA%\MXHPublisher`, gồm database, media đã
nhập, log, ảnh chụp bằng chứng và hồ sơ trình duyệt TikTok.

## Build lại từ mã nguồn

Cài Python 3.12 x64 và Google Chrome, rồi chạy tại thư mục repository:

```powershell
python -m venv .venv
.\scripts\fetch_ffprobe.ps1
.\scripts\build_windows.ps1
.\scripts\smoke_windows.ps1
.\scripts\package_windows.ps1
```

`fetch_ffprobe.ps1` tải đúng FFmpeg 8.1.2 từ gyan.dev và dừng ngay nếu SHA-256
không khớp. Kết quả cuối nằm trong `release\` gồm ZIP và checksum. Quy trình
không yêu cầu hoặc đọc token Facebook/TikTok.

## Giới hạn của bản thử nghiệm

- Đây là bản `UNSIGNED-TEST`, chưa phải installer và chưa ký mã.
- CI chỉ kiểm tra hệ thống/đóng gói, không đăng thử Facebook hoặc TikTok.
- Trước khi dùng tài khoản chính, phải kiểm thử thủ công trên Fanpage và tài
  khoản TikTok thử theo hướng dẫn trong README.
