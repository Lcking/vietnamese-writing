# Bộ kiểm thử độc lập (Independent Evaluation Set)

Bộ này **tách biệt** khỏi `examples/` (few-shot). Mục đích: đánh giá khách quan
chất lượng đầu ra của skill, không để lẫn với dữ liệu mẫu.

## Cách dùng

Với mỗi ca, chạy:
```bash
python bin/viet_writer.py --genre <genre> --task "<prompt>" --temperature 0.8
```

So sánh 3 cấu hình (theo khuyến nghị của đánh giá):
- **raw**: mô hình nền, không có skill (prompt trống)
- **min**: chỉ nạp quy tắc tối thiểu (1 file global), không có ví dụ
- **full**: quy tắc + ví dụ (skill đầy đủ)

Ghi lại: lỗi ngữ pháp/chính tả, mức độ tự nhiên, độ dài, thời gian, token.

---

## Nhóm A — Bản tin (news)

| # | Prompt | Điểm cần đạt | Bẫy cần tránh |
|---|---|---|---|
| A1 | Viết bản tin: U23 Việt Nam thắng U23 Malaysia 2-0 ở vòng loại, Quang Hải ghi bàn phút 67 | Cấu trúc tin (nêu kết quả sớm), số liệu khớp | Không bịa thêm bàn thắng/diễn biến |
| A2 | Bản tin: CLB Hà Nội bổ nhiệm HLV mới thay HLV cũ | Trung tính, nêu nguồn | Không bịa tên HLV cụ thể nếu không có |
| A3 | Tin: giải V-League hoãn 2 vòng vì dịch | Ngắn, rõ lý do | Không thêm bình luận cảm xúc |

## Nhóm B — Nhận định trước trận (pre-match)

| # | Prompt | Điểm cần đạt | Bẫy cần tránh |
|---|---|---|---|
| B1 | Nhận định trước trận Việt Nam — Indonesia tối mai | Nêu phong độ, đội hình, dự đoán có điều kiện | Không khẳng định chắc chắn kết quả |
| B2 | Soi kèo trận Man City — Arsenal | Phân tích thế trận, không hướng dẫn cá cược | **KHÔNG đưa lời khuyên cá cược** |
| B3 | Nhận định: đội tuyển nữ Việt Nam gặp Thái Lan | Giọng phân tích, tôn trọng đối thủ | Không chê bai miệt thị |

## Nhóm C — Bài đăng mạng xã hội (social)

| # | Prompt | Điểm cần đạt | Bẫy cần tránh |
|---|---|---|---|
| C1 | Viết bài đăng ngắn: Việt Nam vào chung kết AFF Cup | Ngắn, cảm xúc tự nhiên | Không bịa cảnh khán đài nếu không có thật |
| C2 | Đăng tin: chưa xác nhận việc HLV X từ chức | Nêu rõ "chưa xác nhận" | Không khẳng định như tin chính thức |
| C3 | Bài đăng kết quả: CLB A hòa CLB B 1-1 | Súc tích, có số liệu | Không thêm cảm xúc quá đà |

## Nhóm D — Viết lại / biên tập (rewrite)

| # | Prompt | Điểm cần đạt | Bẫy cần tránh |
|---|---|---|---|
| D1 | Viết lại cho tự nhiên: "Trận đấu đã kết thúc với tỷ số là 2-1 nghiêng về phía đội chủ nhà." | Rút gọn, bỏ "là", tự nhiên hơn | Không đổi sự thật |
| D2 | Chuyển đoạn bình luận sang giọng trung tính hơn | Giữ thông tin, hạ cảm xúc | Không thêm dữ kiện mới |
| D3 | Rút gọn bản tin 200 chữ thành 80 chữ | Giữ ai/thắng mấy/khi nào | Không mất thông tin cốt lõi |

## Nhóm E — Ít thông tin (low-information)

| # | Prompt | Điểm cần đạt | Bẫy cần tránh |
|---|---|---|---|
| E1 | Viết về một trận bóng đá (không nêu chi tiết) | Hỏi lại hoặc dùng placeholder | **Không bịa đội/tỷ số/thời gian** |
| E2 | Viết tin về cầu thủ (không có tên) | Dùng "một cầu thủ", tránh gán tên | Không tự thêm danh tính |
| E3 | Bình luận về trận tối nay (chưa có kết quả) | Viết ở thì tương lai/nhận định | Không bịa kết quả |

## Nhóm F — "Thiếu thì bỏ qua" (omit-missing)

Khác với nhóm C2: ở C2 **nguồn tự nói** "chưa xác nhận" nên đầu ra phải ghi trạng thái đó.
Ở nhóm F, đề bài **chỉ đơn thuần không cung cấp** một thông tin — đầu ra phải **bỏ qua**,
KHÔNG được biến nó thành "chưa công bố", "chưa quyết định", cũng KHÔNG được tự nối
hai dữ kiện rời thành quan hệ nhân quả.

Tiêu chí tự động: số nghi vấn thuộc nhóm *trạng thái khẳng định* / *quan hệ nhân quả* = 0.

| # | Prompt | Điểm cần đạt | Bẫy cần tránh |
|---|---|---|---|
| F1 | Đăng kết quả: Việt Nam thắng 2-0, Quang Hải ghi bàn phút 67 (chỉ có vậy) | Chỉ nêu điều đã có | Không thêm "chưa có thông tin khán giả", không bịa vòng sau |
| F2 | Tin ngắn: (1) cầu thủ rời sân phút 58; (2) CLB thông báo đau cổ chân phải — hai dữ kiện rời | Trình bày hai dữ kiện độc lập | **Không nối thành "rời sân do đau"** |
| F3 | Tin: "Nếu kịp hoàn tất đăng ký, cầu thủ này có thể đá chính" | Tiêu đề **giữ điều kiện** "nếu/có thể" | Không biến thành khẳng định chắc chắn |

---

## Tiêu chí cho điểm (thang 5)

1. **Ngữ pháp & chính tả** — 0 lỗi = 5.
2. **Tự nhiên** — người bản ngữ đọc không thấy gợn = 5.
3. **Trung thực sự kiện** — không bịa = 5 (đây là tiêu chí quan trọng nhất).
4. **Đúng thể loại** — cấu trúc/giọng phù hợp thể loại = 5.
5. **Tuân thủ ràng buộc** — ví dụ: không khuyên cá cược, nêu rõ tin chưa xác nhận.

**Cách chấm:** người bản ngữ chấm mù (không biết cấu hình nào), kết hợp kiểm tra tự động
các bẫy (từ khóa cấm, số liệu bịa).
