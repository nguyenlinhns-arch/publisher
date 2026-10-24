# Zalo Linh — phát hành tự động bằng yêu cầu phiên bản

Sau khi chủ máy cấu hình một lần môi trường ký phát hành và bộ cập nhật cục bộ, ChatGPT có thể tạo một tệp JSON mới tại thư mục này. Việc đẩy tệp lên main tự kích hoạt GitHub Actions; không phải mở Actions và bấm chạy mỗi phiên bản.

Mẫu file 0.9.21-stable.json (giá trị ID/SHA bên dưới phải được lấy từ bản thực tế, không tự bịa):

```json
{
  "schema": "zalo-linh.release-request.v1",
  "channel": "stable",
  "version": "0.9.21",
  "source_file_id": "REAL_GOOGLE_DRIVE_FULL_RELEASE_ZIP_ID",
  "sha256": "64_LOWERCASE_HEX_CHARACTERS_FROM_FULL_RELEASE_ZIP",
  "qa_file_id": "REAL_GOOGLE_DRIVE_WINDOWS_E2E_QA_RECEIPT_ID",
  "approval_state": "APPROVED_BY_OWNER"
}
```

Yêu cầu phải do chủ sở hữu phê duyệt; không tạo khi chỉ có ZIP toolkit/.diff chưa phải bản phát hành đầy đủ. Trình chạy tự động sẽ từ chối thiếu chữ ký của signer, thiếu QA Windows, không đủ file, nguồn Drive nằm ngoài thư mục staging, hoặc phiên bản không tăng.

Stable giữ nguyên dữ liệu hai tài khoản; ứng dụng PC chỉ cập nhật qua launcher được quản trị viên Windows/V7 cấp phép. Beta chỉ phục vụ QA và KHÔNG tự cài.
