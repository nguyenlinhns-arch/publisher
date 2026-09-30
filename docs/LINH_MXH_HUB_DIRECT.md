# Linh MXH — Hub Direct

Action chuẩn: `schedule_video_dual_stream`.

Mục tiêu: Hub thực hiện việc chọn đúng video, tìm ngày trống và điều phối hai luồng.
Mọi mutation Facebook/TikTok phải đi qua backend của MXH Video Tool bằng
`videoPublish` / `video_publish_bridge`. Cửa sổ GUI không cần ở foreground,
nhưng MXH Video Tool bridge là executor bắt buộc; Hub không tự thay thế bằng một
publisher/provider path khác.

## Cách gọi

Sau khi cài package từ repo này, Hub gọi:

```powershell
linh-mxh-hub --request-file <duong-dan-json>
```

Hoặc:

```powershell
python -m mxh_publisher.hub_direct_cli --request-file <duong-dan-json>
```

## Contract

Hub phải truyền đúng mapping hiện có của từng luồng. Engine không tự suy đoán
Luồng 1/2 là Facebook hay TikTok.

```json
{
  "action": "schedule_video_dual_stream",
  "video_title": "TÊN VIDEO NGUYÊN BẢN",
  "preferred_time": "09:00",
  "stream_1_offset_days": 2,
  "minimum_lead_minutes": 60,
  "commit": true,
  "stream_2": {
    "stream_id": "luong-2",
    "destinations": {
      "facebook": "PAGE_ID",
      "tiktok": "@ACCOUNT"
    },
    "browser_profile_dir": "C:\\...\\profile-luong-2"
  },
  "stream_1": {
    "stream_id": "luong-1",
    "destinations": {
      "facebook": "PAGE_ID",
      "tiktok": "@ACCOUNT"
    },
    "browser_profile_dir": "C:\\...\\profile-luong-1"
  }
}
```

Chỉ khai báo các nền tảng thực sự thuộc luồng đó.

## Quy tắc lịch

- Luồng 2 ưu tiên 09:00 hôm nay.
- Nếu không còn đủ lead time hoặc ngày đó đã có bài trên chính luồng đó, lùi +1 ngày.
- Luồng 1 bắt đầu từ ngày thực tế của Luồng 2 + 2 ngày lúc 09:00.
- Nếu bận, tiếp tục lùi +1 ngày.
- Mỗi luồng tối đa 01 bài/ngày.
- Không tạo thời điểm trong quá khứ.

## Exact title và chống trùng

- Resolve video bằng title khớp 100%.
- Nếu cùng title trỏ tới nhiều file video khác nhau, action dừng thay vì đoán.
- Engine tái sử dụng idempotency của Repository theo account/video/nội dung/phút đăng.
- Có thêm receipt idempotency ở cấp job Linh MXH.
- Retry cùng job trả receipt cũ; không tạo thêm bài.
- Nếu một nền tảng đã `scheduled/published` còn nền tảng kia vẫn `pending/retry_wait`,
  Hub chỉ chạy tiếp nền tảng còn thiếu; không replay nền tảng đã thành công.
- Nếu remote outcome UNKNOWN/PARTIAL hoặc đang `processing/uploading/awaiting_confirmation`,
  chỉ readback; không blind retry.

## Trạng thái receipt

- `PLANNED`: mới preflight.
- `PREPARED`: hai lịch đã được khóa trong local repository, chưa xác nhận remote.
- `DONE`: remote dispatcher xác nhận tất cả đích ở trạng thái scheduled/published/existing.
- `DONE_EXISTING`: hai lịch đã tồn tại đúng yêu cầu.
- `NEEDS_ACTION`: có đích cần thao tác/xác nhận thêm.
- `SUBMITTED_UNVERIFIED`: MXH Video Tool đã có thể gửi mutation nhưng provider
  chưa có receipt xác minh; chỉ readback, tuyệt đối không blind retry.
- `NEEDS_ACTION`: trạng thái cho biết chưa thể tự tiếp tục an toàn.
- `PARTIAL`: có lỗi xác định ở ít nhất một đích.
- `ERROR`: request/validation lỗi.

Chỉ `DONE` và `DONE_EXISTING` được coi là hoàn tất toàn bộ.
`SUBMITTED_UNVERIFIED` không phải lỗi retry; lần chạy sau phải đối soát trước.

## Thứ tự thực thi

1. Resolve video một lần.
2. Query lịch và chọn ngày Luồng 2.
3. Query lịch và chọn ngày Luồng 1.
4. Preflight chống trùng.
5. Tạo hai local schedule.
6. Giao mutation cho MXH Video Tool backend theo từng stream profile.
7. Đọc delivery/provider state và ghi receipt.
8. Nếu receipt chưa authoritative, giữ `SUBMITTED_UNVERIFIED` và chỉ reconcile.
9. Không yêu cầu cửa sổ MXH Video Tool ở foreground.

Chrome/provider UI (nếu MXH Video Tool cần) thuộc trách nhiệm của MXH Video Tool.
Hub không gọi trực tiếp provider và không replay mutation chỉ vì timeout hoặc tiến
trình con trả về trạng thái chưa xác minh.
