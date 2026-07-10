# ffprobe cho bản Windows

Trước khi chạy `scripts/build_windows.ps1`, đặt tệp Windows 64-bit:

```text
bin/ffprobe.exe
```

Chỉ lấy từ bản phân phối FFmpeg đáng tin cậy được liên kết tại [ffmpeg.org/download.html](https://ffmpeg.org/download.html). Không commit toàn bộ FFmpeg hoặc tệp tải từ nguồn không rõ ràng.

Build script cố ý dừng nếu thiếu `ffprobe.exe`; ứng dụng không được phát hành khi chưa có khả năng kiểm tra video.

