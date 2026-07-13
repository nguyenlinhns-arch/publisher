# MXH Video Editor v1.1.0

Ứng dụng Windows độc lập để cắt và dựng video dọc 9:16. Bản này không có chức
năng Facebook, TikTok, lịch đăng, token hoặc điều khiển trình duyệt.

## Kết quả video

- Cắt cố định **6,2 giây đầu** và **4 giây cuối**.
- Giữ toàn bộ thời lượng còn lại, không ép tối đa 90 giây.
- Xuất MP4 H.264/AAC, 1080×1920, 30 fps.
- Dùng `assets/nen.png` làm nền xanh mặc định.
- Đặt video ngang ở giữa khung.
- Tiêu đề chữ trắng, viền đen, tối đa ba dòng.
- Thêm dòng `Thầy Linh - Tuyển Thợ Mỏ`.
- Dấu `-` trong tiêu đề tạo một dòng mới trên video.
- Dùng font Be Vietnam Pro ExtraBold hỗ trợ đầy đủ tiếng Việt.
- Phát âm thanh mở đầu mặc định trong 0,36 giây đầu, sau đó tiếp tục âm thanh gốc.
- Không thay đổi hoặc xóa video gốc.

Video thành phẩm được lưu mặc định tại:

```text
Videos\MXH Video Editor
```

Ứng dụng có nút mở video, mở thư mục và xóa video thành phẩm. Lệnh xóa chỉ chấp
nhận MP4 nằm trực tiếp trong thư mục thành phẩm.

## Sử dụng bản Windows

1. Giải nén toàn bộ ZIP.
2. Chạy `MXHVideoEditor\MXHVideoEditor.exe`.
3. Chọn video gốc.
4. Nhập tiêu đề.
5. Nhấn **SỬA VÀ LƯU VIDEO**.
6. Chọn video trong danh sách để mở hoặc xóa.

Ứng dụng được build ở chế độ Windows GUI nên không mở cửa sổ CMD.

## Phát triển

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest -q
.\scripts\fetch_ffprobe.ps1
.\scripts\build_windows.ps1
.\scripts\smoke_windows.ps1
.\scripts\package_windows.ps1
```

Mã biên tập dùng FFmpeg/ffprobe. Hai executable Windows được tải từ gói FFmpeg
đã khóa checksum trong `scripts/fetch_ffprobe.ps1`.
