# MXH Publisher v0.4.2

- Bỏ hoàn toàn chốt kiểm tra tối đa 90 giây.
- Sau khi bỏ 6,2 giây đầu và 4 giây cuối, ứng dụng giữ nguyên toàn bộ thời lượng
  còn lại, kể cả video dài hơn 90 giây.
- Bước kiểm tra video và bước biên tập đều không còn phát sinh lỗi `DURATION`
  chỉ vì video dài.
- Bổ sung kiểm thử hồi quy với video đầu ra dài 148,4 giây.

Khung xanh, tiêu đề trên video, dòng nhận diện và phiên Edge dùng chung giữa
Facebook/TikTok giữ nguyên như v0.4.1.
