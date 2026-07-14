# MXH Video Editor v1.2.2

Ứng dụng Windows độc lập để cắt và dựng video dọc 9:16. Bản này không có chức
năng Facebook, TikTok, lịch đăng, token hoặc điều khiển trình duyệt.

## Kết quả video

- Cắt cố định **6,2 giây đầu** và **4 giây cuối**.
- Giữ toàn bộ thời lượng còn lại, không ép tối đa 90 giây.
- Xuất MP4 H.264/AAC, 1080×1920, 30 fps.
- Dùng `assets/nen.png` làm nền tin tức xanh đen mặc định, có ánh cam và
  cyan; tệp nền không chứa chữ, logo, khung hay giao diện mạng xã hội.
- Đặt video ngang ở giữa và tiêu đề bên dưới như kết cấu ban đầu.
- Tiêu đề chữ trắng, viền đen, tối đa ba dòng.
- Thêm dòng `THẦY LINH - TUYỂN THỢ MỎ` nhỏ ở góc trên như ảnh mẫu;
  không còn dòng thương hiệu ở phía dưới.
- Dấu `-` trong tiêu đề tạo một dòng mới trên video.
- Dùng Anton theo mẫu chữ đậm, cao và hẹp cho cả tiêu đề và dòng thương hiệu; cỡ tiêu đề tự điều chỉnh theo độ dài.
- Phát âm thanh mở đầu mặc định trong 0,36 giây đầu, sau đó tiếp tục âm thanh gốc.
- Không thay đổi hoặc xóa video gốc.

Video thành phẩm được lưu mặc định tại:

```text
Videos\MXH Video Editor
```

Ứng dụng có nút mở video, mở thư mục và xóa video thành phẩm. Lệnh xóa chỉ chấp
nhận MP4 nằm trực tiếp trong thư mục thành phẩm.

Ứng dụng hỗ trợ xử lý hàng loạt:

- Chọn nhiều video trong một lần.
- Tự lấy tên file làm tiêu đề ban đầu.
- Chọn từng dòng để sửa riêng tiêu đề.
- Xử lý tuần tự để tránh làm máy quá tải.
- Một video lỗi không làm dừng các video còn lại.
- Hiển thị tiến độ và trạng thái của từng video.

## Sử dụng bản Windows

1. Giải nén toàn bộ ZIP.
2. Chạy `MXHVideoEditor\MXHVideoEditor.exe`.
3. Nhấn **Chọn nhiều video** và chọn một hoặc nhiều file MP4.
4. Chọn từng dòng nếu cần sửa riêng tiêu đề.
5. Nhấn **SỬA TẤT CẢ VIDEO**.
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
