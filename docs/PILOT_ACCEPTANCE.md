# Tiêu chí nghiệm thu pilot trước tài khoản chính

Thực hiện bằng Fanpage và TikTok thử, một video không nhạy cảm.

- [ ] Workflow GitHub `Windows build` xanh; ZIP khớp SHA-256.
- [ ] Giải nén trên Windows 10/11 sạch; `doctor --system-only` có 0 lỗi chặn.
- [ ] Lưu Page ID/token vào Credential Manager và TikTok account vào config.
- [ ] `doctor` và `Dry-run` có 0 lỗi chặn.
- [ ] Happy path: TikTok đúng account/giờ, sau đó Facebook đúng Page/giờ.
- [ ] Sau giờ đăng, đối chiếu link và trạng thái cả hai nền tảng.
- [ ] Ngắt mạng trước upload: không có remote post, chỉ retry sau khi kiểm tra.
- [ ] Ngắt mạng trong upload: trạng thái an toàn, không tạo upload thứ hai.
- [ ] Ngắt mạng sau finish Facebook: lưu `video_id`, chuyển `UNKNOWN`, worker chỉ
  đối soát và không upload lại.
- [ ] Đổi Page/TikTok account sau duyệt: app phải chặn.
- [ ] Tạo hai bài giống nhau cùng giờ/account: app phải chặn bài thứ hai.
- [ ] CAPTCHA/2FA: app không tự xử lý và không lưu screenshot.
- [ ] Khởi động lại sau crash: lease hết hạn được phục hồi an toàn.
- [ ] Backup/restore database và gỡ Task Scheduler thành công.

Chỉ chuyển sang tài khoản chính khi tất cả mục đạt và đã lưu lại log, link cùng
kết quả kiểm tra. Code signing là bước riêng trước khi phát hành rộng.
