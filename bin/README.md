# FFmpeg cho bản Windows

Trước khi chạy `scripts/build_windows.ps1`, dùng script có kiểm tra SHA-256:

```powershell
.\scripts\fetch_ffprobe.ps1
```

Script sẽ đặt hai tệp Windows 64-bit tại:

```text
bin/ffprobe.exe
bin/ffmpeg.exe
```

Nguồn/version/checksum được khóa trong script và ghi lại trong
`THIRD_PARTY_NOTICES.md`. Không commit binary hoặc thay bằng tệp tải từ nguồn
không rõ ràng.

Build script cố ý dừng nếu thiếu `ffprobe.exe` hoặc `ffmpeg.exe`; ứng dụng không
được phát hành khi chưa có khả năng kiểm tra và biên tập video.
