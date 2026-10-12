# Changelog

## v1.4.6 (2026-10-13) — 第四轮方案(A/B/C/D/E)

### A. large 档瘦身(P0)
- large 档提示从 24,499 → **4,184 字符**(目标 ≤8,000 ✓)
- large 档不再注入全局语言规则(17,813 字符)与长体裁文件;改用专用精简卡
  `references/cards/ket_qua_large.md`(2,133 字符)
- small 档保持卡片方案(3,432 字符),两档明确不同
- 新增规则 A2 不向读者解释规则/数据;A3 比分动词主语(球队,或"球员+đưa/giúp+队");
  A4 胜者在前的大比分写法

### B. 事实块纯数据化(P0)
- 去掉指令性标签(`→`、`dùng cho`、`dùng đúng`、加粗)
- 首行:`Chủ nhà · Khách` + `Kết quả`(两种写法都给出)
- 进球过程以**球队**作主语,比分按该队视角
- 写作提示单独成段并标注 `(KHÔNG đưa vào bài)`
- 缺分钟时只列"球员 + 球队",不写逐球比分,不放 `?`

### C. 检查器误报修复(P0)
- C1 `normalize_output()`:清理首行标题的 `**`/`#`(不调用模型);清理后仍有才判 S11
- C2 S1:顺序不可靠时只核对带分钟的进球,期望动词不含 `?`
- C3 S14 接收 task 文本;允许集合 = facts 名 + facts["context"] + task 里的大写词串
- C4 S12 改为按句判断(修跨句误报;补 `giai đoạn cuối trận` 等词)

### D. 检查器补漏(P1)
- S15 赛果方向(非平局写"hòa";nghiêng về 方向;胜者主语后小比分在前)——阻断
- S16 进球数(单球球员被写 cú đúp/hat-trick)——阻断
- S17 决胜球归属——阻断;顺序不可靠时仅提示
- S18 元说明(向读者解释规则/数据)——阻断
- S19 重复事件——提示
- S20 动词主语(球员名直连动词)——提示

### E. 评测
- E1 run_eval 新增 G5-G9(5 场真实比赛)
- E2 full 组走 `viet_writer.write` 真实路径(含 tier/修订/normalize)
- E3 新增 `--tier`;结果记录 system_chars / revise_triggered
- E4 回归表转为内置测试(TestE4RegressionTable)
- 事实块快照存 `eval/regression/real_matches_20261012/snapshots/`

### 验收
- 82 例测试全过(43+30+9);check_quality 17 项 0 问题
- 参考改写零命中;5 场事实块无 `**`/`→`/`dùng cho`/`dùng đúng`

---


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
