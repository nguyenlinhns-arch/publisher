# Thiết lập Facebook Fanpage thử

1. Dùng một Fanpage thử, không bắt đầu bằng Page chính.
2. Tạo/chọn Meta App do chính chủ quản lý và cấu hình theo tài liệu Reels
   Publishing API hiện hành của Meta.
3. Cấp Page access token cho đúng Page. Quyền cụ thể phụ thuộc trạng thái và loại
   Meta App; kiểm tra lại trong tài liệu Meta tại thời điểm cấu hình.
4. Trong `Thiết lập/kiểm tra`, nhập Page ID dạng số và token. Token chỉ được lưu
   trong Windows Credential Manager.
5. Khởi động lại ứng dụng, chạy `doctor` và `Dry-run`.
6. Tạo một video thử không nhạy cảm, hẹn cách ít nhất 60 phút.
7. Sau khi gửi, đối chiếu `video_id`, trạng thái và permalink trên chính Page.

Không dán token vào GitHub, email, ảnh chụp hoặc file cấu hình. Khi nghi ngờ lộ
token, thu hồi/đổi token tại Meta ngay. Bản V0.2.0 xác nhận token tồn tại cục bộ;
việc token còn hạn, đúng Page và đủ quyền chỉ được chứng minh bằng lần gọi API
trên Page thử.

Tài liệu chính thức:
<https://developers.facebook.com/documentation/video-api/guides/reels-publishing>
