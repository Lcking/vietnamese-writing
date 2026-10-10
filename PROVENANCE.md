# Provenance & Evidence Chain — 提炼证据链

Bản ghi này lưu lại **cách** nội dung trong `references/` và `examples/` được tạo ra,
để bất kỳ ai cũng có thể kiểm tra lại (reproducible). Đây là bằng chứng cần thiết vì
quy mô dữ liệu thô (303GB / 10GB) **không tự động đồng nghĩa với chất lượng**.

## 1. Nguồn dữ liệu (Data source)

- **Dataset:** WanJuan-Vietnamese (万卷丝路-越南语)
- **Nhà xuất bản:** Shanghai Artificial Intelligence Laboratory (OpenDataLab) và Corpus Data Alliance
- **Giấy phép:** CC BY 4.0
- **Quy mô gốc:** ~303GB (7 nhóm chủ đề, ~50 shard jsonl)
- **Repo nguồn:** https://github.com/opendatalab/WanJuan3.0

**Hạn chế cần biết:** WanJuan là ngữ liệu **văn bản đã làm sạch**, KHÔNG kèm URL trang web,
tên nhà xuất bản, hay thời gian đăng. Vì vậy các trường `source_url`, `publisher`,
`published_at` trong `examples/*.jsonl` được đánh dấu `"unavailable"` — trung thực là
không bịa. Chuỗi truy xuất nguồn gốc dừng ở mức giấy phép của dataset, KHÔNG phải ở
từng bài báo cụ thể.

## 2. Quy trình tạo references/ (rules)

- **Đầu vào:** mẫu trích từ WanJuan-Vietnamese (đa chủ đề), phân tích đặc điểm ngôn ngữ
  theo thể loại.
- **Phương pháp:** trích xuất đặc điểm văn phong (cấu trúc câu, từ ngữ, nhịp điệu) —
  KHÔNG lưu văn bản nguồn thô vào skill.
- **Kiểm tra của người:** các quy tắc trong `_global_loi_thuong_gap.md` đã được rà lại;
  phần "ví dụ sai" do mô hình tự sinh đã bị loại bỏ (xem mục 4).

## 3. Quy trình tạo examples/ (few-shot)

Chạy: `python bin/extract_corpus.py --pick <football_corpus.jsonl> --examples ./examples/football`

Các bước lọc (theo thứ tự):
1. **Cổng liên quan bóng đá trước:** `classify()` phải cho `confidence == high`
   (xét từ khóa bóng đá + loại trừ tín hiệu môn khác như bóng rổ, quần vợt, bóng chuyền, golf).
2. **Cổng nhanh:** content phải chứa ít nhất một từ khóa bóng đá cứng.
3. **Lọc độ dài:** 800–4500 ký tự.
4. **Lọc nhiễu:** loại quảng cáo/cá độ/SEO (bắn cá, casino, soi cầu, tạp chí doanh nghiệp...),
   áp dụng cả cho **title** lẫn **content**.
5. **Khử trùng:** SHA-256 trên văn bản đã chuẩn hóa (ổn định giữa các lần chạy).
6. **Gán nhãn chủ đề đa nhãn:** một bài có thể vào nhiều nhóm chủ đề.

Mỗi bản ghi lưu trường: `id, theme, title, content, len, source_url, publisher,
published_at, collected_at, original_id, source_dataset, content_sha256, language,
sport, genre, review_status, license_or_attribution`.

## 4. Sửa đổi thủ công quan trọng (đã khắc phục lỗi cũ)

- `_global_loi_thuong_gap.md`: **viết lại toàn bộ.** Bản cũ chứa đầu ra thất bại của mô hình
  (câu "Xin lỗi, tôi sẽ viết lại..." lặp lại, ví dụ sai trùng với ví dụ đúng). Bản mới chỉ
  giữ nguyên tắc tổng quát đã kiểm chứng, bỏ ví dụ sai tự sinh.
- `football_binh_luan.md`: sửa `da橙` -> `da cam`; sửa nhầm biệt danh "Người đặc biệt"
  (vốn của Mourinho) gán cho CR7.
- `van_hoc.md`: sửa cặp ví dụ đúng/sai giống hệt nhau (Hogwarts).
- Tiêu đề các file `references/*.md`: chuyển sang **thuần tiếng Việt** (bỏ chú thích tiếng Trung).

## 5. Kiểm tra tự động

Chạy: `python bin/check_quality.py` — kiểm tra JSONL hợp lệ, trường nguồn gốc, khử trùng,
ngôn ngữ thuần (không lẫn chữ Hán/Nhật/Hàn), ví dụ đúng/sai trùng nhau, ngân sách prompt,
định tuyến thể loại. Kết quả mong đợi: **0 vấn đề, 0 cảnh báo**.

## 6. Hash tài liệu (tại lần cập nhật này)

| Tệp | SHA-256 (rút gọn) |
|---|---|
| bin/extract_corpus.py | 1ff86ace... |
| bin/viet_writer.py | d043b2ec... |
| bin/check_quality.py | 53d4ef2f... |
| src/llm_client.py | 7d170c97... |
| examples/football/*.jsonl (tổng) | 3cda1870... |

## 7. Điều KHÔNG được tuyên bố

- KHÔNG tuyên bố skill này "thay thế" một mô hình được tinh chỉnh (fine-tune). Đây là
  skill **bơm kiến thức qua prompt** (prompt-injection), không huấn luyện lại trọng số.
- KHÔNG tuyên bố đã bao phủ mọi phong cách viết. Đặc biệt phần mạng xã hội hiện dựa trên
  hướng dẫn biên tập, chưa có bộ bài đăng mạng xã hội thực đã kiểm duyệt đầy đủ.
- KHÔNG đảm bảo tính đúng đắn của sự kiện — model cơ sở vẫn có thể sai sự thật.
