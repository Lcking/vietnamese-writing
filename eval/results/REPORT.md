# Kết quả chạy (raw / min / full)

Mô hình: `qwen-3.8-27b-awq` (local, vLLM :8005), `enable_thinking=false`, temperature 0.8, max_tokens 3000.
Thời điểm: chạy ngày 2026-10-10. 24 lượt (8 ca × 3 cấu hình).

## Bảng chỉ số

| Ca | Nhóm | raw (chữ/s) | min (chữ/s) | full (chữ/s) |
|---|---|---|---|---|
| A1 | news | 579 / 23.2s | 623 / 54.2s | 1678 / 113.1s |
| A2 | news | 801 / 18.4s | 687 / 39.9s | 977 / 82.1s |
| B1 | pre_match | 3687 / 107.1s | 2444 / 136.6s | 1594 / 165.5s |
| B2 | pre_match | 3004 / 147.2s | 3679 / 153.5s | 3299 / 90.2s |
| C1 | social | 133 / 23.2s | 297 / 13.2s | 154 / 28.5s |
| C2 | social | 507 / 14.8s | 142 / 9.7s | 157 / 28.7s |
| D1 | rewrite | 55 / 7.0s | 61 / 19.4s | 37 / 37.6s |
| E1 | low_info | 805 / 41.6s | 128 / 42.9s | 923 / 118.5s |

## Kết luận phần tự động

- **0 vi phạm bẫy** trên cả 8 ca × 3 cấu hình (sau khi sửa nhận biết phủ định —
  các 'vi phạm' ban đầu đều là dương tính giả: mô hình viết 'không phải lời khuyên cá cược').
- **0 ca thiếu thông tin bắt buộc** (A1 giữ 2-0, C2 nêu 'chưa xác nhận', D1 giữ 2-1).
- `full` **KHÔNG** dài hơn `raw` (1102 vs 1196 ký tự TB) — độ dài không phải lợi thế của skill.
- `full` chậm nhất (83s vs 48s) do system prompt lớn nhất (đổi lấy chất lượng — cần blind review xác nhận).

## Điều CHƯA thể kết luận (cần người bản ngữ)

Phần tự động chỉ đo **ràng buộc cứng**. Nó KHÔNG đo được:
- mức độ tự nhiên / đúng văn phong
- tính đúng đắn sự kiện (có bịa không)
- 'full' có thực sự tốt hơn 'raw' không, hay chỉ khác về độ dài/giọng

→ Cần chấm mù theo `blind_review.md` trước khi kết luận skill 'tốt hơn' mô hình nền.