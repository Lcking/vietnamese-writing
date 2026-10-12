#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
distill_corpus.py — Chưng cất (distill) kho ngữ liệu bóng đá bằng mô hình local.

Quy trình 3 tầng (chạy được trên 10GB / 2.5 triệu dòng, không thể gọi model cho từng dòng):
  Tầng 1 (heuristic, rẻ): quét toàn bộ corpus, chấm điểm heuristic
        (độ dài, tỉ lệ câu hoàn chỉnh, mật độ từ khoá bóng đá, nhiễu, chữ in hoa...).
        → chỉ giữ top N% vào "bể ứng viên".
  Tầng 2 (model, đắt): Qwen chấm ĐIỂM theo rubric 4 tiêu chí, mỗi lần gọi chấm
        nhiều bài cùng lúc (batch), buộc trả JSON. → điểm chất lượng thật.
  Tầng 3: chọn top theo hạn ngạch thể loại → ghi file distill output.

Dùng:
    # Tầng 1: quét toàn bộ, lấy 20k ứng viên
    python bin/distill_corpus.py scan --src .../football_corpus.jsonl --out /tmp/pool.jsonl --pool 20000

    # Tầng 2: chấm điểm bằng model (chạy nền, có --limit để chạy thử)
    python bin/distill_corpus.py score --pool /tmp/pool.jsonl --out /tmp/scored.jsonl --limit 200

    # Tầng 3: chọn theo hạn ngạch
    python bin/distill_corpus.py select --scored /tmp/scored.jsonl --out examples/football/...
"""
import argparse
import hashlib
import json
import os
import random
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# ---------------------------------------------------------------- Tầng 1
FOOT_WORDS = ["bóng đá", "cầu thủ", "trận đấu", "đội bóng", "bàn thắng", "ghi bàn",
              "huấn luyện viên", "hlv", "v-league", "champions league", "world cup",
              "aff cup", "đội tuyển", "penalty", "thẻ đỏ", "vòng loại", "chuyển nhượng",
              "ngoại hạng anh", "la liga", "serie a", "bundesliga", "tỷ số", "hiệp",
              "luân lưu", "đội hình", "khán đài", "cổ động viên", "trọng tài"]
NOISE = re.compile(
    r"bắn cá|casino|soi cầu|đổi thưởng|cá độ|nhà cái|fun88|w88|m88|kèo nhà cái"
    r"|tải app|khuyến mãi|đăng ký ngay|hotline|http|www\.|"
    r"Xem thêm|Đọc tiếp|VIDEO:|Clip:|liên hệ quảng cáo", re.I)
# chữ Trung Quốc / tiếng Anh dính bài
FOREIGN = re.compile(r"[\u4e00-\u9fff]")


def heuristic_score(title, content):
    """Điểm 0–100, rẻ tiền nhưng lọc được phần lớn rác."""
    c = content.strip()
    n = len(c)
    s = 0.0
    # 1) độ dài lý tưởng 300–1500 ký tự (đủ dài để có văn cảnh, không quá dài)
    if 300 <= n <= 1500:
        s += 25
    elif 150 < n < 3000:
        s += 12
    else:
        return 0, "length"
    # 2) nhiễu / quảng cáo / chữ Hán → loại ngay
    if NOISE.search(c[:400]) or FOREIGN.search(c):
        return 0, "noise"
    # 3) mật độ từ khoá bóng đá
    low = c.lower()
    hits = sum(1 for w in FOOT_WORDS if w in low)
    if hits >= 3:
        s += 20
    elif hits >= 1:
        s += 8
    else:
        return 0, "no-football"
    # 4) cấu trúc câu: tỉ lệ câu "hoàn chỉnh" (có dấu chấm và độ dài 20+ ký tự)
    sents = [x for x in re.split(r"[.!?…]\s+", c) if len(x.strip()) >= 20]
    if sents:
        ratio = sum(len(x) for x in sents) / max(1, n)
        s += 20 * min(1.0, ratio * 1.15)
    # 5) dấu hiệu báo chí tốt: dấu ngoặc kép (trích dẫn), con số cụ thể
    if c.count('"') >= 2:
        s += 10
    digits = len(re.findall(r"\b\d+\b", c))
    s += min(10, digits * 2)
    # 6) tiêu đề không phải dạng menu/SEO
    if title.count("-") >= 2 and len(title) > 90:
        s -= 15
    # 7) tỉ lệ chữ in hoa bất thường (spam)
    upper_ratio = sum(1 for ch in c if ch.isupper()) / max(1, n)
    if upper_ratio > 0.25:
        s -= 20
    return max(0.0, min(100.0, s)), "ok"


def cmd_scan(args):
    """Tầng 1: quét toàn bộ corpus bằng heuristic."""
    pool = []
    seen = set()
    n = 0
    t0 = time.time()
    with open(args.src, encoding="utf-8", errors="replace") as f:
        for line in f:
            n += 1
            if args.max_scan and n > args.max_scan:
                break
            try:
                r = json.loads(line)
            except Exception:
                continue
            title = (r.get("title") or "").strip()
            content = (r.get("content") or "").strip()
            if not title or not content:
                continue
            score, why = heuristic_score(title, content)
            if score < args.min_score:
                continue
            h = hashlib.sha256(content.encode()).hexdigest()
            if h in seen:
                continue
            seen.add(h)
            pool.append({
                "title": title, "content": content, "len": len(content),
                "h_score": round(score, 1), "original_id": r.get("id"),
                "category": r.get("category"), "content_sha256": h,
            })
    # giữ top theo heuristic
    pool.sort(key=lambda x: -x["h_score"])
    pool = pool[:args.pool]
    with open(args.out, "w", encoding="utf-8") as f:
        for r in pool:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    dt = time.time() - t0
    print(f"Tầng 1 xong: quét {n:,} dòng trong {dt:.0f}s, "
          f"pool = {len(pool):,} ứng viên (>= {args.min_score} điểm) -> {args.out}")
    if pool:
        scores = [p["h_score"] for p in pool]
        print(f"  h_score: min {min(scores)}, median {sorted(scores)[len(scores)//2]}, max {max(scores)}")


# ---------------------------------------------------------------- Tầng 2
RUBRIC = """Bạn là biên tập viên kiểm duyệt chất lượng văn bản tiếng Việt.

Chấm ĐIỂM mỗi bài dưới đây theo 4 tiêu chí (mỗi thang 0–10):
- "fluency": câu chữ trôi chảy, tự nhiên như người Việt viết (không dịch máy, không lủng củng)
- "journalism": đúng cấu trúc tin/bài báo (có thông tin cụ thể: ai, việc gì, khi nào; trích dẫn hợp lý)
- "cleanliness": SẠCH — không quảng cáo, không SEO, không metadata trang web (giờ đăng, tên đăng nhập), không câu cụt
- "uniqueness": thông tin cụ thể riêng (không phải câuGeneric nước đôi vô nghĩa)

CHỈ trả về MỘT dòng JSON duy nhất, dạng:
[{"i": 0, "fluency": 8, "journalism": 7, "cleanliness": 9, "uniqueness": 6}, ...]
(i = số thứ tự bài trong danh sách. Không giải thích thêm.)"""


def _parse_json_array(text):
    """Qwen hay bọc thêm chữ; tìm chuỗi JSON array đầu tiên."""
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
        return arr if isinstance(arr, list) else None
    except Exception:
        return None


def cmd_score(args):
    """Tầng 2: Qwen chấm điểm theo batch."""
    from llm_client import LLMClient
    client = LLMClient({
        "base_url": os.environ.get("VIET_LLM_BASE_URL", "http://192.168.31.34:8005/v1"),
        "api_key": os.environ.get("VIET_LLM_API_KEY", "dummy"),
        "model": os.environ.get("VIET_LLM_MODEL", "qwen-3.8-27b-awq"),
        "disable_thinking": True,
        "timeout": int(os.environ.get("VIET_LLM_TIMEOUT", "150")),
    })
    pool = [json.loads(l) for l in open(args.pool, encoding="utf-8")]
    if args.limit:
        pool = pool[:args.limit]
    # xáo trộn để batch không dồn một chủ đề (nếu --shuffle)
    if args.shuffle:
        random.Random(42).shuffle(pool)

    B = args.batch
    done = failed = 0
    t0 = time.time()
    out_f = open(args.out, "w", encoding="utf-8")
    for i in range(0, len(pool), B):
        batch = pool[i:i + B]
        listing = "\n\n".join(
            f"### Bài {j}\nTiêu đề: {r['title']}\nNội dung: {r['content'][:1200]}"
            for j, r in enumerate(batch))
        try:
            res = client.chat(RUBRIC, listing, max_tokens=1400, temperature=0.1)
            arr = _parse_json_array(res.text)
        except Exception as e:
            arr = None
            print(f"  [batch {i//B}] LỖI model: {e}", file=sys.stderr)
        if not arr or len(arr) < len(batch) // 2:
            failed += 1
            print(f"  [batch {i//B}] parse kém (nhận {0 if not arr else len(arr)}/{len(batch)}), bỏ batch", file=sys.stderr)
            continue
        by_i = {a.get("i"): a for a in arr if isinstance(a, dict)}
        for j, r in enumerate(batch):
            a = by_i.get(j)
            if not a:
                continue
            try:
                q = (float(a.get("fluency", 0)) + float(a.get("journalism", 0)) +
                     float(a.get("cleanliness", 0)) + float(a.get("uniqueness", 0))) / 4
            except Exception:
                continue
            r["q_fluency"] = a.get("fluency")
            r["q_journalism"] = a.get("journalism")
            r["q_cleanliness"] = a.get("cleanliness")
            r["q_uniqueness"] = a.get("uniqueness")
            r["q_score"] = round(q, 2)
            out_f.write(json.dumps(r, ensure_ascii=False) + "\n")
        done += len(batch)
        if (i // B) % 5 == 0:
            dt = time.time() - t0
            print(f"  tiến độ: {done}/{len(pool)} bài, {failed} batch lỗi, "
                  f"{dt:.0f}s ({dt/max(1,done)*1000:.0f} ms/bài)", flush=True)
    out_f.close()
    print(f"Tầng 2 xong: {done} bài được chấm điểm -> {args.out} ({failed} batch lỗi)")


# ---------------------------------------------------------------- Tầng 3
def cmd_select(args):
    """Tầng 3: chọn top theo hạn ngạch."""
    rows = [json.loads(l) for l in open(args.scored, encoding="utf-8")]
    rows.sort(key=lambda r: -r.get("q_score", 0))
    # lọc ngưỡng
    rows = [r for r in rows if r.get("q_score", 0) >= args.min_q]
    print(f"{len(rows)} bài đạt >= {args.min_q} điểm chất lượng")
    # phân bổ theo độ dài (ngắn/trung/dài) để data phong phú
    buckets = {"ngan": [], "vua": [], "dai": []}
    for r in rows:
        n = r["len"]
        k = "ngan" if n < 500 else ("vua" if n <= 1200 else "dai")
        buckets[k].append(r)
    per = args.total // 3
    selected = []
    for k in ("ngan", "vua", "dai"):
        selected.extend(buckets[k][:per])
    # nếu thiếu, lấy thêm từ nhóm còn dư
    if len(selected) < args.total:
        chosen_ids = {r["content_sha256"] for r in selected}
        for r in rows:
            if len(selected) >= args.total:
                break
            if r["content_sha256"] not in chosen_ids:
                selected.append(r)
                chosen_ids.add(r["content_sha256"])
    with open(args.out, "w", encoding="utf-8") as f:
        for r in selected:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    # thống kê
    qs = [r["q_score"] for r in selected]
    print(f"Đã chọn {len(selected)} bài -> {args.out}")
    print(f"  q_score: min {min(qs)}, median {sorted(qs)[len(qs)//2]}, max {max(qs)}")
    from collections import Counter
    print(f"  phân bổ độ dài: {dict(Counter('ngan' if r['len']<500 else ('vua' if r['len']<=1200 else 'dai') for r in selected))}")


def main():
    ap = argparse.ArgumentParser(description="Chưng cất ngữ liệu bằng model local")
    sub = ap.add_subparsers(dest="cmd", required=True)

    p1 = sub.add_parser("scan", help="Tầng 1: quét heuristic toàn bộ corpus")
    p1.add_argument("--src", required=True)
    p1.add_argument("--out", required=True)
    p1.add_argument("--pool", type=int, default=20000, help="số ứng viên tối đa giữ lại")
    p1.add_argument("--min-score", type=float, default=40, help="ngưỡng heuristic (0-100)")
    p1.add_argument("--max-scan", type=int, default=0)
    p1.set_defaults(func=cmd_scan)

    p2 = sub.add_parser("score", help="Tầng 2: model chấm điểm theo batch")
    p2.add_argument("--pool", required=True)
    p2.add_argument("--out", required=True)
    p2.add_argument("--batch", type=int, default=5, help="số bài mỗi lần gọi model")
    p2.add_argument("--limit", type=int, default=0, help="chỉ chấm N bài đầu (0 = hết)")
    p2.add_argument("--shuffle", action="store_true")
    p2.set_defaults(func=cmd_score)

    p3 = sub.add_parser("select", help="Tầng 3: chọn top theo hạn ngạch")
    p3.add_argument("--scored", required=True)
    p3.add_argument("--out", required=True)
    p3.add_argument("--total", type=int, default=240)
    p3.add_argument("--min-q", type=float, default=6.0, help="ngưỡng điểm chất lượng 0-10")
    p3.set_defaults(func=cmd_select)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
