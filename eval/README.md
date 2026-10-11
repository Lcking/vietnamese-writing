# Đánh giá độc lập (Independent Evaluation)

Thư mục này chứa **bộ đánh giá tách biệt** khỏi dữ liệu few-shot (`examples/`),
nhằm đo chất lượng đầu ra của skill một cách khách quan.

## Thành phần

- `evalset.md` — bộ ca kiểm thử (5 nhóm: news / pre_match / social / rewrite / low_info)
- `results/` — kết quả chạy thật (đầu ra + chỉ số), sinh bởi `bin/run_eval.py`
- `blind_review.md` — mẫu chấm điểm mù cho **người bản ngữ**

## Quy trình 3 bước

### Bước 1 — Chạy 3 cấu hình

```bash
export VIET_LLM_BASE_URL=... VIET_LLM_API_KEY=... VIET_LLM_MODEL=...
python bin/run_eval.py --out eval/results
```

Ba cấu hình được so sánh trên **cùng một mô hình, cùng dữ kiện đầu vào**:

| Cấu hình | Nạp gì |
|---|---|
| `raw` | Không có skill (system prompt rỗng) |
| `min` | Chỉ quy tắc tối thiểu (1 file core), không ví dụ |
| `full` | Skill đầy đủ (quy tắc + ví dụ few-shot) |

Chỉ số ghi lại: số ký tự, thời gian, `finish_reason`, token, và **vi phạm bẫy tự động**
(từ cấm như "nên cược", số liệu phải khớp như "2-0").

### Bước 2 — Chấm tự động (đã có)

`run_eval.py` tự kiểm tra các bẫy: với mỗi ca có quy tắc `forbid` / `expect`, nó đánh dấu
nếu đầu ra chứa từ bị cấm hoặc thiếu thông tin bắt buộc (ví dụ ca C2 phải có "chưa xác nhận").

### Bước 2b — Phát hiện dữ kiện bịa (`bin/check_fabrication.py`)

Trong so sánh nhiều mô hình, phát hiện quan trọng nhất là: **mô hình tầm trung / mô hình
nhỏ chạy cấu hình `full` (prompt dài) hay CHÈN dữ kiện cụ thể mà đề bài không cung cấp** —
mốc thời gian ("trưa nay"), hành động tổ chức ("chính thức thông báo"), cảnh sân đấu
("khán đài rộn ràng"), con số/tỉ số. Chỉ mô hình mạnh mới giữ được kỷ luật "không bịa".

Công cụ này **đánh dấu** (không phán quyết) những chỗ cần đối chiếu:

```bash
# kiểm 1 đầu ra
python bin/check_fabrication.py --task "..." --text-file output.txt
# quét toàn bộ kết quả eval
python bin/check_fabrication.py --scan-eval eval/results
```

Nó bỏ qua các câu mang phủ định ("không bịa", "chưa xác nhận"), và so với đề bài để loại
mảnh vốn có sẵn trong đề. **Kết quả là danh sách nghi vấn cho người đọc, không phải điểm số.**

> **Khuyến nghị triển khai:** nếu dùng mô hình tầm trung / mô hình nhỏ, chạy cấu hình `min`
> (quy tắc ngắn) thay vì `full`, và bật `check_fabrication.py` như một lớp kiểm tra đầu ra.

### Bước 3 — Chấm mù bởi người bản ngữ (**cần người thật**)

Đây là phần **không thể tự động hóa**: một biên tập viên tiếng Việt chấm điểm mù
(không biết đầu ra nào thuộc cấu hình nào), theo thang 5 ở `blind_review.md`.

> **Lưu ý trung thực:** nếu chưa có người chấm mù, kết quả chỉ là **một nửa** của đánh giá.
> Phần tự động (chỉ số + vi phạm bẫy) là khách quan nhưng *không* đo được độ tự nhiên
> và tính đúng đắn sự kiện. Không được tuyên bố "đã đánh giá đầy đủ" nếu chưa có bước 3.

## Tiêu chí chấm (thang 5)

1. **Ngữ pháp & chính tả** — 0 lỗi = 5
2. **Tự nhiên** — người bản ngữ đọc không gợn = 5
3. **Trung thực sự kiện** — không bịa = 5 *(tiêu chí quan trọng nhất)*
4. **Đúng thể loại** — cấu trúc/giọng phù hợp = 5
5. **Tuân thủ ràng buộc** — ví dụ: không khuyên cá cược, nêu rõ tin chưa xác nhận = 5

## Cảnh báo về quy mô dữ liệu

303GB (ngữ liệu gốc) và ~10GB (trích xuất) là **quy mô nguyên liệu**, KHÔNG phải
điểm chất lượng hay điểm hiệu quả. Điểm chất lượng chỉ đến từ bước 2 + bước 3 ở trên.
