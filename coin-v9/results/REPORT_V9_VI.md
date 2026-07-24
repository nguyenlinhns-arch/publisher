# COIN V9 — NGHIÊN CỨU GIAO DỊCH HÀNG NGÀY & ĐÒN BẨY

- Thời gian tạo: 2026-07-24T18:11:10.671755+00:00
- Số trial thực tế: 12,000
- Đạt yêu cầu tối thiểu 10.000 trial: True
- Holdout khóa: 2025-07-20 00:00:00+00:00 → 2026-07-01 00:00:00.005000+00:00
- Vốn mô phỏng: 10,000,000 VND
- Đòn bẩy được stress: 10, 20, 30, 40, 50, 60, 70, 80x
- Winner đầy đủ: 0
- Winner strict bootstrap + DSR: 0
- Winner đồng thời đạt ưu tiên ≥4 lệnh/ngày: 0

## Champion tỷ lệ thắng (chỉ xét expectancy dương)
```json
null
```

## Champion tần suất
```json
null
```

## Champion lợi nhuận
```json
null
```

## Champion chịu chi phí 24 bps
```json
null
```

## Ensemble được chọn bằng pre-holdout
```json
null
```

## Overlay đòn bẩy an toàn tốt nhất
```json
null
```

## Kết luận phương pháp
Đòn bẩy chỉ khuếch đại lãi/lỗ và không làm tăng tỷ lệ thắng của tín hiệu. Kết quả chỉ được gọi là ứng viên triển vọng khi còn dương sau phí, funding, stress chi phí, drawdown và kiểm tra khoảng cách thanh lý bảo thủ. Không có lệnh thật nào được gửi.