#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_short_posts.py — Trích bài đăng NGẮN tiếng Việt về bóng đá từ ngữ liệu.

对应评审要求:重建社交部分需要「真正的越南语足球短帖」,区分 5 种帖:
  - ket_qua    : kết quả / báo nhanh (赛果快讯)
  - lich_thi_dau: lịch / đội hình trước trận (赛前赛程)
  - chua_xac_nhan: tin chưa xác nhận / tin đồn (未确认消息)
  - quan_diem  : bình luận / ý kiến (观点)
  - hoi_dap    : tương tác / hỏi đáp (互动帖)

CHỈ trích xuất (không tự động cào web). Kết quả dùng làm few-shot cho thể loại
social_post, hoặc để soi lại văn phong mạng.

Dùng:
    python bin/extract_short_posts.py --src <football_corpus.jsonl> \
        --out examples/football/social_post.jsonl --per-type 15
"""
import argparse, hashlib, json, os, re, sys
from collections import defaultdict

FOOT = ["bóng đá", "cầu thủ", "trận đấu", "đội bóng", "bàn thắng", "ghi bàn", "thủ môn",
        "huấn luyện viên", "hlv", "v-league", "champions league", "world cup", "aff cup",
        "đội tuyển việt nam", "penalty", "phạt góc", "thẻ đỏ", "thẻ vàng", "vòng loại",
        "chuyển nhượng", "chiêu mộ", "ngoại hạng anh", "la liga", "serie a", "bundesliga",
        "cúp", "tỷ số", "hiệp một", "hiệp hai", "luân lưu", "đội hình"]
NONFOOT = ["bóng rổ", "quần vợt", "tennis", "bóng chuyền", "golf", "cầu lông", "bóng bàn",
           "điền kinh", "bơi lội", "đua xe", "cricket", "nba", "bóng ném"]
BAD = re.compile(r"bắn cá|casino|soi cầu|đổi thưởng|cá độ|nhà cái|fun88|w88|m88|"
                 r"http|www\.|tỷ lệ kèo|kèo nhà cái|đăng ký|khuyến mãi|tải app|"
                 r"SOSUB|Euro\d|\.org|liên hệ|hotline|quảng cáo|"
                 r"Vstar|Vegas\d|VZ\d|VN\d{2,}|Bet\d|Win\d{2,}|188|789|Zbet|"
                 r"Doanh nghiệp Việt Nam|Thể Thao, Cup|tinh khiết|"
                 r"tinh thể|sản xuất cúp|kỷ niệm chương|"
                 r"\bAuthor at\b|\bPage \d+ of\b|townshelter|^\s*Link\b|"
                 r"\bArchives?\b|\bAdmin\b", re.I)
# dấu hiệu tiêu đề là menu/tag site
SITETAG = re.compile(r"\|\s*(tag|thanh niên|vnexpress|dân trí|bóng đá|24h|zing|archives)|"
                     r"^\s*(tag|trang chủ|archives|video\s*-|\w+\s+archives)", re.I)
# dấu hiệu nội dung là mục từ bách khoa / văn bản hành chính (loại khỏi social)
WIKI = re.compile(r"Đội hình hiện tại\s*Sửa đổi|Tính đến ngày \d|Ghi chú: Quốc kỳ|"
                  r"^\s*Sửa đổi|Danh sách|Tham khảo|Liên kết ngoài", re.I)

# phân loại 5 nhóm
DEF_TYPE = [
    ("ket_qua", re.compile(r"\d+\s*[-–]\s*\d+|tỷ số|kết quả|thắng|thua|hòa|đánh bại", re.I)),
    ("lich_thi_dau", re.compile(r"đội hình|lịch thi đấu|sẽ gặp|ra sân|trước trận|đá chính", re.I)),
    ("chua_xac_nhan", re.compile(r"chưa xác nhận|tin đồn|rộ tin|được cho là|có thể|có khả năng", re.I)),
    ("hoi_dap", re.compile(r"\?|theo bạn|bạn nghĩ|dự đoán|bình chọn", re.I)),
    ("quan_diem", re.compile(r"theo tôi|tôi nghĩ|đánh giá|nhận định|bình luận|quan điểm", re.I)),
]


def is_football(t):
    tl = t.lower()
    if any(w in tl for w in NONFOOT):
        return False
    return any(w in tl for w in FOOT)


def clean(t):
    t = re.sub(r"\b\d{1,2}:\d{2},?\s*\d{1,2}/\d{1,2}/\d{4}\b", "", t)   # bỏ timestamp
    t = re.sub(r"https?://\S+", "", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def classify_type(text):
    for name, rx in DEF_TYPE:
        if rx.search(text):
            return name
    return "quan_diem"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--per-type", type=int, default=15)
    ap.add_argument("--max-scan", type=int, default=0, help="0 = quét hết")
    args = ap.parse_args()

    picked = defaultdict(list)
    seen = set()
    n = scanned = 0
    target_each = args.per_type

    with open(args.src, encoding="utf-8", errors="replace") as f:
        for line in f:
            n += 1
            if args.max_scan and n > args.max_scan:
                break
            try:
                r = json.loads(line)
            except Exception:
                continue
            c = clean(r.get("content", "") or "")
            title = clean(r.get("title", "") or "")
            # đặc trưng bài NGẮN: 60–700 ký tự
            if not (60 <= len(c) <= 700):
                continue
            if not title or len(title) < 15:
                continue
            if BAD.search(title) or BAD.search(c[:150]):
                continue
            if SITETAG.search(title):
                continue
            if WIKI.search(c) or WIKI.search(title):
                continue
            if not is_football(title + " " + c):
                continue
            h = hashlib.sha256(c.encode("utf-8")).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            t = classify_type(title + " " + c)
            if len(picked[t]) >= target_each:
                if all(len(picked[k]) >= target_each for k in
                       ("ket_qua", "lich_thi_dau", "chua_xac_nhan", "quan_diem", "hoi_dap")):
                    break
                continue
            picked[t].append({
                "type": t, "title": title, "content": c, "len": len(c),
                "source_url": "unavailable", "publisher": "unavailable",
                "published_at": "unavailable", "collected_at": "2026-10-10",
                "original_id": r.get("id"), "content_sha256": h,
                "language": "vi", "sport": "football", "genre": "social_post",
                "review_status": "auto_short", "license_or_attribution":
                "WanJuan-Vietnamese (Shanghai AI Laboratory, OpenDataLab) — CC BY 4.0",
                "excerpt_span": f"0:{len(c)}",
            })
            scanned += 1

    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    # ghi phẳng: mỗi dòng 1 bài, kèm trường type
    total = 0
    with open(args.out, "w", encoding="utf-8") as fo:
        for t, items in picked.items():
            for it in items:
                fo.write(json.dumps(it, ensure_ascii=False) + "\n")
                total += 1
    print(f"Đã quét {n} dòng, chọn {total} bài ngắn -> {args.out}")
    for t in ("ket_qua", "lich_thi_dau", "chua_xac_nhan", "quan_diem", "hoi_dap"):
        print(f"  {t:15s}: {len(picked[t])}")


if __name__ == "__main__":
    main()
