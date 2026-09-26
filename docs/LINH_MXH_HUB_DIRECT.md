# Linh MXH — Hub Direct

Action chuẩn: `schedule_video_dual_stream`.

Mục tiêu: Hub thực hiện toàn bộ việc chọn đúng video, tìm ngày trống và đặt hai luồng
mà không cần mở cửa sổ MXH Video Tool.

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
- Nếu remote outcome UNKNOWN/PARTIAL, không blind retry.

## Trạng thái receipt

- `PLANNED`: mới preflight.
- `PREPARED`: hai lịch đã được khóa trong local repository, chưa xác nhận remote.
- `DONE`: remote dispatcher xác nhận tất cả đích ở trạng thái scheduled/published/existing.
- `DONE_EXISTING`: hai lịch đã tồn tại đúng yêu cầu.
- `NEEDS_ACTION`: có đích cần thao tác/xác nhận thêm.
- `PARTIAL`: có lỗi hoặc kết quả remote chưa chắc chắn.
- `ERROR`: request/validation lỗi.

Chỉ `DONE` và `DONE_EXISTING` được coi là hoàn tất toàn bộ.

## Thứ tự thực thi

1. Resolve video một lần.
2. Query lịch và chọn ngày Luồng 2.
3. Query lịch và chọn ngày Luồng 1.
4. Preflight chống trùng.
5. Tạo hai local schedule.
6. Dispatch remote theo từng stream profile.
7. Ghi một receipt cuối.
8. Không mở MXH Video Tool GUI.

Nếu remote dispatcher hiện tại phải dùng Chrome, Chrome có thể được dùng như lớp
publisher; yêu cầu "không mở MXH Video Tool" vẫn được giữ. Khi Hub có native action/API
cho từng nền tảng, inject dispatcher đó để bỏ cả thao tác trình duyệt.
