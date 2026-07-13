# Tiêu chí nghiệm thu pilot trước tài khoản chính

Thực hiện bằng Fanpage và TikTok thử, một video không nhạy cảm.

- [ ] Workflow GitHub `Windows build` xanh; ZIP khớp SHA-256.
- [ ] Giải nén trên Windows 10/11 sạch; `doctor --system-only` có 0 lỗi chặn.
- [ ] Đăng nhập Facebook/TikTok trong cùng Chrome riêng của app và giữ Chrome mở.
- [ ] `doctor` và `Dry-run` có 0 lỗi chặn.
- [ ] Happy path: TikTok đúng account/giờ, sau đó Facebook đúng Page/giờ.
- [ ] Sau giờ đăng, đối chiếu link và trạng thái cả hai nền tảng.
- [ ] Ngắt mạng trước upload: không có remote post, chỉ retry sau khi kiểm tra.
- [ ] Ngắt mạng trong upload: trạng thái an toàn, không tạo upload thứ hai.
- [ ] Sau khi file đã vào trình duyệt: trạng thái `Chờ xác nhận`, bấm lại không
  upload lần hai.
- [ ] Đổi Page/TikTok account sau duyệt: app phải chặn.
- [ ] Tạo hai bài giống nhau cùng giờ/account: app phải chặn bài thứ hai.
- [ ] CAPTCHA/2FA: app không tự xử lý và không lưu screenshot.
- [ ] Khởi động lại sau crash: lease hết hạn được phục hồi an toàn.
- [ ] Backup/restore database và gỡ Task Scheduler thành công.

Chỉ chuyển sang tài khoản chính khi tất cả mục đạt và đã lưu lại log, link cùng
kết quả kiểm tra. Code signing là bước riêng trước khi phát hành rộng.
