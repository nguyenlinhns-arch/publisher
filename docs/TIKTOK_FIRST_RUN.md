# TikTok — lần chạy đầu

1. Bấm `Mở kết nối`; ứng dụng mở TikTok bằng Google Chrome thường.
2. Tự đăng nhập, xử lý CAPTCHA/2FA rồi bấm `Kiểm tra lại`.
3. Giữ cửa sổ Chrome do app mở; không đóng trước khi đăng.
4. Bấm `Đăng TikTok`; ứng dụng gắn vào chính cửa sổ TikTok Studio đó và dùng
   phiên đang đăng nhập.
5. Ứng dụng tự chọn video, điền caption, bật lịch, điền ngày/giờ Việt Nam và bấm
   nút cuối khi nhận diện chắc chắn đủ các điều khiển.
6. Nếu TikTok yêu cầu CAPTCHA/2FA hoặc giao diện đã đổi, tự hoàn tất phần được
   yêu cầu; ứng dụng sẽ dừng trước cú bấm không chắc chắn.
7. Khi app báo đã đăng/lên lịch, có thể bấm `Đăng FB`.

Nếu TikTok đổi giao diện, không tìm thấy preview hoặc chuyển sang miền/path lạ,
ứng dụng phải dừng ở `NEEDS_ACTION`. Nếu cú bấm cuối đã xảy ra nhưng kết quả chưa
rõ, tác vụ chuyển `UNKNOWN` và không được tự gửi lại cho tới khi đã đối soát.
