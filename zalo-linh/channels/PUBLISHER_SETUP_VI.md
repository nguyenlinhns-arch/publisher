# Zalo Linh — đường phát hành phiên bản dùng lâu dài

Ngày triển khai kỹ thuật: 24/10/2026. **Chưa có bản 0.9.21 đã ký/cài lên Windows.**

## Hai kênh

1. **BETA** — `zalo-linh/channels/beta.json` trong `nguyenlinhns-arch/publisher`. Chỉ chứa metadata bản thử; không được launcher Zalo Linh hoặc Guard tự động cài. Bản mã vá RC1 0.9.21 hiện là *toolkit chưa ký* và không đủ điều kiện nâng cấp.
2. **STABLE** — file có chữ ký `G:\My Drive\ZaloLinhUpdates\stable.json`, mirror `zalo-linh/stable.json` trên GitHub và file ZIP đúng `G:\My Drive\ZaloLinhUpdates\releases\zalo-<version>.zip`. Launcher chỉ nhận đúng chữ ký Ed25519 với khóa công khai hiện đã ghim, đúng SHA-256, đủ manifest và phiên bản **cao hơn bản đã cài**.

**Khôi phục** — bản cũ vẫn nằm ở `versions/<version>` trong thư mục cài Zalo Linh; `previous.txt`/biên nhận và backup SQLite là những chốt để launcher quay lại nếu READY thất bại. Không đổi/ghi đè hai hồ sơ Chrome, CRM, ledger.

## Bộ mã phát hành đã tạo

- `scripts/zalo_linh_release.py`: xác minh signed feed, bản ZIP và SHA từng file; từ chối phiên bản cũ, URL lạ, path traversal, zip bomb, thiếu manifest; hàm ký Ed25519 dùng khóa **lấy từ kho bí mật của nhà phát hành** (không có trong mã nguồn).
- `scripts/zalo_linh_release_drive.py`: thực thi trên GitHub Actions trong môi trường được bảo vệ, chỉ nhận file ID gói đã nằm trong thư mục staging Drive; cho phép đánh giá BETA hoặc phát hành STABLE sau khi có Windows E2E PASS gắn với đúng SHA.
- `.github/workflows/zalo-linh-signed-release.yml`: quy trình thủ công một lần để phê duyệt phát hành; ứng dụng PC sau đó tự nhận khi kiểm tra định kỳ. Không tự đăng bản chưa ký.
- `.github/workflows/zalo-linh-release-ci.yml`: kiểm thử chữ ký/hình thức ZIP và các điều kiện fail-closed khi sửa mã pipeline.
- `tests/test_zalo_release.py`: 22 trường hợp kiểm thử đã PASS tại phiên tạo.

## Khởi tạo một lần — chủ quản trị làm qua giao diện bảo mật

**Trên PC**: dùng quy trình được Windows/V7 cho phép để chấp thuận ứng dụng Guard cố định `G:\My Drive\ZaloLinhUpdates\staging\ZaloLinhAutoUpdateGuard_1.0_OWNER_INSTALL.exe`. Guard đăng ký kiểm tra nguồn STABLE mỗi 6 giờ. Nếu bị SmartScreen/PC Control chặn vì EXE chưa ký, phải ký/xác minh chính thức — không tắt cảnh báo hay vượt chính sách. Sau khi hoạt động kiểm tra được `%APPDATA%\ThayLinhZaloChatFix\auto-update-guard-status.json`.

**Trên GitHub**: một lần kết nối tài khoản dịch vụ Drive chỉ được chia sẻ thư mục ZaloLinhUpdates staging/releases và file stable; cấu hình các GitHub environment secrets sau (không dán vào ChatGPT):

- `ZALO_LINH_DRIVE_SERVICE_ACCOUNT_JSON`: JSON xác thực dịch vụ Drive riêng, không phải đăng nhập Zalo.
- `ZALO_LINH_SIGNING_SEED_B64`: khóa ký Ed25519 *của nhà phát hành*, phải khớp khóa công khai của `ZaloLinh.exe`. Lưu trong protected environment `zalo-linh-production`. Không đọc/xuất lại khóa bí mật từ PC qua chat.
- `ZALO_LINH_STAGING_FOLDER_ID`, `ZALO_LINH_RELEASES_FOLDER_ID`, `ZALO_LINH_STABLE_FILE_ID`: IDs từ Google Drive của đúng bộ hồ sơ đã có. Không cấp quyền toàn Drive cho dịch vụ.

Bật yêu cầu *reviewers* cho environment `zalo-linh-production`. Nếu thiếu bất kỳ secret hoặc biên nhận QA hợp lệ, pipeline từ chối phát hành, không tự suy diễn là thành công.

## Cách ra bản mới sau này

1. ChatGPT sửa và kiểm thử *trên bản sao* của mã phiên bản đang cài → tạo ZIP **đầy đủ** `VERSION.txt + app/*.py|js + payload_manifest.json`, mỗi file được hash; không phát hành `.diff` hoặc toolkit làm bản cài.
2. Đưa ZIP vào Drive staging. Windows QA sinh biên nhận `zalo-linh.windows-e2e.v1` gắn version + SHA, kiểm tra khởi động, hai tài khoản, hộp thư, SQLite, rollback và không gửi tin tự động.
3. Trigger workflow GitHub `Zalo Linh signed release channels`: chọn STABLE, nhập Drive file ID, phiên bản, SHA, QA file ID. Workflow xác minh, yêu cầu reviewer, ký đúng khóa, sao chép sang Drive releases, cập nhật `stable.json`, mirror GitHub.
4. Guard PC mỗi 6 giờ xác minh bản mới ký → chỉ khi PC rảnh và Zalo Linh đóng mới khởi chạy stable launcher; launcher tự sao lưu, kiểm tra READY và khôi phục nếu lỗi. Không cần tải EXE cài lại cho từng phiên bản.

**Đặc biệt:** Hiện PC đang dùng 0.9.20, stable đã ký trên Drive/GitHub mới là 0.9.14. Chưa bật update cho đến khi có bản >=0.9.21 đã ký và chương trình Guard được chủ PC cho phép chạy.
