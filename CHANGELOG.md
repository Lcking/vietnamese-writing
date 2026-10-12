# Changelog

Mọi thay đổi đáng chú ý của skill này được ghi ở đây.
Định dạng theo [Keep a Changelog](https://keepachangelog.com/); đánh số [SemVer](https://semver.org/).

## [Unreleased] — Đợt sửa theo đánh giá vòng 2 (Claude review)

Ưu tiên: **sự thật > prompt gọn > chất lượng ngữ liệu > đánh giá/tài liệu**.

### Thay đổi KHÔNG TƯƠNG THÍCH (breaking)
- **`social_post` và `football_tin_tuc` mặc định dùng profile `lite`**, không còn `full`.
  Prompt ngắn hơn nhiều (khoảng 5–6k ký tự thay vì ~36k). Muốn hành vi cũ, thêm `--profile full`.
- **Lệnh gọi cần thoát ra khi API lỗi timeout**: lỗi đọc (`TimeoutError`/`socket.timeout`)
  giờ raise `LLMError(kind="timeout")` và **không tự retry** (tránh tính phí trùng).
  Ai đang dựa vào việc retry timeout cần xử lý lại ở tầng gọi.

### Added
- `prompts/system_vi_writer.md`: **nguyên tắc ba tầng sự thật** (đã xác nhận / nguồn nói
  chưa xác nhận / đề không cung cấp → bỏ qua) + hai lệnh cấm (không nối nhân quả;
  tiêu đề phải giữ điều kiện "nếu/có thể").
- `bin/check_fabrication.py`: bộ phát hiện dữ kiện bịa, thêm hai lớp mới:
  **trạng thái khẳng định** ("chưa được công bố", "đang chờ") và **quan hệ nhân quả**
  ("do", "vì", "sau khi"). Phủ định chỉ miễn trừ **trong cùng câu**; chuẩn hoá trước khi
  so (gạch ngang, ngày, số chữ, "được").
- `tests/test_check_fabrication.py`: 9 ca kiểm thử (T1–T9), chạy `python -m pytest tests/`.
- `bin/clean_examples.py`: dọn metadata lẫn trong thân bài (dấu thời gian, tác giả, "Nguồn:")
  mà **không xoá cả bài**.
- `eval/evalset.md`: **nhóm F** ("thiếu thì bỏ qua") + `run_eval.py` kiểm bằng detector.
- `bin/check_quality.py`: kiểm tra **không có chữ Hán** trong `references/` và `prompts/`.
- `SKILL.md`: bảng thể loại thêm `football_pre_match`, `football_analysis`, `social_post`;
  mục giải thích `--profile`; cây thư mục cập nhật.
- `bin/summarize_eval.py`: tách báo cáo thành **[1] vi phạm bẫy** và **[2] nghi vấn dữ kiện bịa**.

### Changed
- `bin/viet_writer.py`: thêm `--profile min|lite|full`, `--post-type`; `pick_examples()`
  lọc theo loại bài, bỏ cắt cứng `content[:1500]` (cắt ở ranh giới câu), loại bài cũ hơn 3 năm,
  gắn nhãn `[Mẫu diễn đạt – không phải dữ kiện]`; `stats.examples_chars` được gán đúng.
- `references/_global_gioi_tu_tro.md`: sửa 4 quy tắc sai ("Trời là đẹp" → phản ví dụ;
  "trà với cà phê" cả hai đều đúng; lược "của" không phải lỗi; bỏ ví dụ "thì" đặt sai vị trí).
- `examples/football/social_post.jsonl`: **xây lại** — 75 bài ngắn, lọc sạch phi bóng đá và
  nhiễu; gắn `type_reviewed: false`. Tài liệu ghi rõ đây **là tin ngắn, không phải bài social thật**.
- 8 file chủ đề khác: dọn nhiễu metadata trong thân (26 bài), bỏ 1 mục xếp hạng futsal.
- `_global_*.md`: gắn header `review_status: unreviewed` (chưa có biên tập viên bản ngữ).

### Fixed
- `src/llm_client.py`: bắt `TimeoutError`/`socket.timeout` ở giai đoạn đọc (kind="timeout");
  5xx ghi log từng lần thử; sửa lỗi `learned.values()` so sánh dict-với-str (luôn đúng).
- `prompts/system_vi_writer.md`: gỡ câu "Chỉ trả về nội dung bài viết" khỏi prompt lõi
  (xung đột với `--format`); định dạng đầu ra giờ theo hợp đồng của bên gọi.

### Known gaps (chưa xử lý, nêu trung thực)
- **Chấm mù bởi người bản ngữ: CHƯA thực hiện** (cần người thật). Mẫu ở `eval/blind_review.md`.
- `type` trong `social_post.jsonl` vẫn là nhãn máy gán, chưa được người xác nhận.
- `_global_*.md` chưa qua biên tập viên bản ngữ (đánh dấu `unreviewed`).

## [v1.2.0] — 2026-10-11
- Ngữ liệu bài đăng ngắn thật cho `social_post` (48 bài, duyệt thủ công).
- Đánh giá so sánh đa model: gpt-6-luna / glm-5.3-flash / qwen local (8 ca × 3 cấu hình).
  Phát hiện chính: model tầm trung/nhỏ **bịa dữ kiện** khi prompt dài.
- `bin/check_fabrication.py` (bản đầu) — lớp kiểm tra đầu ra.
- `eval/results/REPORT-CROSS-MODEL.md`.

## [v1.1.0] — 2026-10-10
- Sửa theo đánh giá vòng 1 (P0/P1/P2): làm sạch bộ quy tắc, viết lại `extract_corpus.py`,
  tách module `src/llm_client.py`, thêm `PROVENANCE.md`, bộ đánh giá độc lập.

## [v1.0.0] — 2026-10-10
- Bản phát hành đầu tiên: skill viết tiếng Việt tập trung bóng đá, tri thức trích từ
  WanJuan-Vietnamese (CC BY 4.0).
