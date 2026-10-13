# ⚠️ Dữ liệu MẪU TẠM (placeholder)

5 file `M1–M5.json` trong thư mục này **KHÔNG phải trận đấu thật**:

- Tên cầu thủ là giả: "Nguyễn Văn A", "Trần Văn B", "Lê Văn C"…
- Phút và sự kiện do người tạo tự sinh ra
- Ngày thống nhất 12/10

Chúng chỉ dùng để kiểm thử **hình dạng** dữ liệu (điểm danh, đội hình,
tỷ số, luân lưu, phản lưới nhà) cho `prepare_facts` và `check_style`, KHÔNG
dùng để đánh giá chất lượng bài viết.

## Cần thay bằng gì

`docs/operations/evidence/vietnamese-writing-v144-realrun-20261012/matches.py`
— bản đã đối chiếu với ≥2 nguồn báo Việt Nam (do phía评审 cung cấp).
Khi có file đó, hãy chạy:

```bash
python bin/load_matches.py <đường-dẫn/matches.py>   # (TODO: viết loader)
```

rồi cập nhật `_eval_map.json` với cùng nội dung nhiệm vụ.

Đến khi thay xong: các test dựa trên 5 file này chỉ kiểm tra logic trình bày,
không phải kết quả trận đấu thật.
