#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
distill_generic.py — 蒸馏 7 大类通用越南语语料(与 distill_corpus.py 同管线,按类扩展)。

Dùng:
    # Tầng 1: quét heuristic một loại (hoặc tất cả)
    python bin/distill_generic.py scan --category news \
        --raw-root /lzcapp/document/Knowledge-vietnem/OpenDataLab___WanJuan-Vietnamese/raw \
        --out /tmp/generic/news_pool.jsonl --pool 3000

    # Tầng 2: model chấm điểm
    python bin/distill_generic.py score --pool /tmp/generic/news_pool.jsonl \
        --out /tmp/generic/news_scored.jsonl --limit 350

    # Tầng 3: chọn top
    python bin/distill_generic.py select --scored /tmp/generic/news_scored.jsonl \
        --out examples/generic/news_top.jsonl --total 40
"""
import argparse
import glob
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

# ---------------------------------------------------------- 域内关键词(每类)
DOMAIN_WORDS = {
    "culture": ["văn hoá", "văn hóa", "truyền thống", "lễ hội", "nghệ thuật",
                "âm nhạc", "điệu nhảy", "ẩm thực", "di sản", "tôn giáo", "đạo",
                "hội họa", "văn học", "ca dao", "tục ngữ"],
    "encyclopedia": ["là một", "là loại", "khái niệm", "định nghĩa", "phân loại",
                     "đặc điểm", "nguồn gốc", "cấu tạo", "chức năng", "thuộc"],
    "general": ["cuộc sống", "gia đình", "bạn bè", "cảm xúc", "kinh nghiệm",
                "mẹo", "cách để", "làm sao", "tại sao", "ý nghĩa"],
    "history_policy": ["lịch sử", "cách mạng", "chiến tranh", "thời kỳ", "triều đại",
                       "chính sách", "nghị quyết", "quyết định", "pháp luật", "nghị định",
                       "đảng", "nhà nước", "bộ chỉ huy", "quốc hội"],
    "local_life": ["đời sống", "người dân", "bà con", "làng", "xã", "phường",
                   "chợ", "huyện", "tỉnh", "cuộc sống thường nhật", "bữa cơm"],
    "news": ["được biết", "theo tin", "phóng viên", "đưa tin", "hôm qua", "sáng nay",
             "chiều nay", "trao đổi", "phát biểu", "cho hay", "theo đó"],
    "professional_field": ["nghiên cứu", "phân tích", "kỹ thuật", "quy trình",
                           "đầu tư", "quản trị", "kinh tế", "luật", "y khoa",
                           "xây dựng", "công nghệ", "giáo dục"],
}
# 通用噪声(比足球版更广)
NOISE = re.compile(
    r"bắn cá|casino|soi cầu|đổi thưởng|cá độ|nhà cái|fun88|w88|m88|kèo nhà cái"
    r"|tài xỉu|game bài|lô đề"
    r"|tải app|khuyến mãi|đăng ký ngay|hotline|http|www\.|"
    r"Xem thêm|Đọc tiếp|VIDEO:|Clip:|liên hệ quảng cáo"
    r"|phần mềm hack|crack|keygen", re.I)
FOREIGN = re.compile(r"[\u4e00-\u9fff]")
# 跨域泄漏:通用 7 类里混入的体育/赌博内容(足球已有专门管线,这里算域外噪声)
SPORT_LEAK = re.compile(
    r"bóng đá|cầu thủ|trận đấu|đội bóng|bàn thắng|ghi bàn|world cup|champions"
    r"|ngoại hạng anh|la liga|serie a|bundesliga|v-league|aff cup|hlv "
    r"|chuyển nhượng|cúp bóng|giải golf|giải vợt|pk10|soi kèo", re.I)


def heuristic_score(content, words, title=""):
    """0-100 启发式分(通用版,无标题参与)。"""
    c = (content or "").strip()
    n = len(c)
    if not (300 <= n <= 2000):
        return 0.0
    s = 25.0
    if NOISE.search(c[:400]) or FOREIGN.search(c):
        return 0.0
    # 跨域泄漏检查:标题+前 600 字符(足球新闻的触发词常在标题)
    probe = ((title or "") + " ") + c[:600]
    if SPORT_LEAK.search(probe):
        return 0.0
    low = c.lower()
    hits = sum(1 for w in words if w in low)
    if hits >= 3: s += 20
    elif hits >= 1: s += 8
    else: return 0.0
    sents = [x for x in re.split(r"[.!?…]\s+", c) if len(x.strip()) >= 20]
    if sents:
        ratio = sum(len(x) for x in sents) / max(1, n)
        s += 20 * min(1.0, ratio * 1.15)
    if c.count('"') >= 2: s += 10
    digits = len(re.findall(r"\b\d+\b", c))
    s += min(10, digits * 2)
    upper_ratio = sum(1 for ch in c if ch.isupper()) / max(1, n)
    if upper_ratio > 0.25: s -= 20
    return max(0.0, min(100.0, s))


def cmd_scan(args):
    words = DOMAIN_WORDS[args.category]
    files = sorted(glob.glob(os.path.join(args.raw_root, args.category, "*", "*.jsonl")))
    if not files:
        print(f"Không tìm thấy jsonl cho {args.category}")
        return
    pool, seen = [], set()
    n = 0
    skipped_sub = 0
    t0 = time.time()
    want_subs = None
    if getattr(args, "sub", None):
        want_subs = {args.sub.lower()}
    elif getattr(args, "sub_any", None):
        want_subs = {s.strip().lower() for s in args.sub_any.split(",") if s.strip()}
    for fp in files:
        with open(fp, encoding="utf-8", errors="replace") as f:
            for line in f:
                n += 1
                if args.max_scan and n > args.max_scan:
                    break
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                # 子体裁过滤(按 labels.level2)
                if want_subs is not None:
                    l2 = (r.get("labels", {}).get("pjwk_cates", {}) or {}).get("level2", [])
                    if isinstance(l2, str):
                        l2 = [l2]
                    got = {str(x).lower() for x in l2}
                    if not (got & want_subs):
                        skipped_sub += 1
                        continue
                content = (r.get("content") or "").strip()
                if not content:
                    continue
                score = heuristic_score(content, words, title=(r.get("title") or ""))
                if score < args.min_score:
                    continue
                h = hashlib.sha256(content.encode()).hexdigest()
                if h in seen:
                    continue
                seen.add(h)
                pool.append({
                    "category": args.category,
                    "title": (r.get("title") or "").strip()[:200],
                    "content": content, "len": len(content),
                    "h_score": round(score, 1),
                    "original_id": r.get("id"), "content_sha256": h,
                    "src_file": os.path.basename(fp),
                })
        if args.max_scan and n > args.max_scan:
            break
    pool.sort(key=lambda x: -x["h_score"])
    pool = pool[:args.pool]
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        for r in pool:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    sub_info = ""
    if want_subs:
        sub_info = f" [sub={','.join(sorted(want_subs))}, bỏ {skipped_sub:,} bài khác nhóm]"
    print(f"[{args.category}]{sub_info} quét {n:,} dòng trong {time.time()-t0:.0f}s -> "
          f"pool {len(pool):,} -> {args.out}")


# ---------------------------------------------------------------- score
RUBRIC = """Bạn là biên tập viên kiểm duyệt chất lượng văn bản tiếng Việt.

Chấm điểm mỗi bài dưới đây theo 4 tiêu chí (thang 0-10):
- "fluency": câu chữ trôi chảy, tự nhiên như người Việt bản địa viết (không dịch máy)
- "informativeness": có thông tin cụ thể, rõ ràng (ai/cái gì/khi nào/như thế nào)
- "cleanliness": SẠCH — không quảng cáo, không SEO, không metadata web (giờ đăng, tên đăng nhập), không câu cụt lửng
- "style": có giá trị làm MẪU cho thể loại (cấu trúc bài rõ, giọng văn phù hợp chủ đề)

CHỈ trả về MỘT dòng JSON: [{"i": 0, "fluency": 8, "informativeness": 7, "cleanliness": 9, "style": 7}, ...]
Không giải thích."""


def _parse_json_array(text):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        return None
    try:
        arr = json.loads(m.group(0))
        return arr if isinstance(arr, list) else None
    except Exception:
        return None


def cmd_score(args):
    from llm_client import LLMClient
    client = LLMClient({
        "base_url": os.environ.get("VIET_LLM_BASE_URL", "http://192.168.31.34:8005/v1"),
        "api_key": os.environ.get("VIET_LLM_API_KEY", "dummy"),
        "model": os.environ.get("VIET_LLM_MODEL", "qwen-3.8-27b-awq"),
        "disable_thinking": True,
        "timeout": 150,
    })
    pool = [json.loads(l) for l in open(args.pool, encoding="utf-8")]
    if args.limit:
        pool = pool[:args.limit]
    if args.shuffle:
        random.Random(7).shuffle(pool)
    B = args.batch
    done = failed = 0
    t0 = time.time()
    out_f = open(args.out, "w", encoding="utf-8")
    for i in range(0, len(pool), B):
        batch = pool[i:i + B]
        listing = "\n\n".join(
            f"### Bài {j}\nTiêu đề: {r.get('title','')[:150]}\nNội dung: {r['content'][:1200]}"
            for j, r in enumerate(batch))
        try:
            res = client.chat(RUBRIC, listing, max_tokens=1400, temperature=0.1)
            arr = _parse_json_array(res.text)
        except Exception as e:
            arr = None
            print(f"  [batch {i//B}] model lỗi: {e}", file=sys.stderr)
        if not arr or len(arr) < len(batch) // 2:
            failed += 1
            continue
        by_i = {a.get("i"): a for a in arr if isinstance(a, dict)}
        for j, r in enumerate(batch):
            a = by_i.get(j)
            if not a:
                continue
            try:
                q = (float(a.get("fluency", 0)) + float(a.get("informativeness", 0)) +
                     float(a.get("cleanliness", 0)) + float(a.get("style", 0))) / 4
            except Exception:
                continue
            r["q_fluency"] = a.get("fluency")
            r["q_informativeness"] = a.get("informativeness")
            r["q_cleanliness"] = a.get("cleanliness")
            r["q_style"] = a.get("style")
            r["q_score"] = round(q, 2)
            out_f.write(json.dumps(r, ensure_ascii=False) + "\n")
        done += len(batch)
        if (i // B) % 10 == 0:
            dt = time.time() - t0
            print(f"  {done}/{len(pool)} ({failed} batch lỗi) {dt:.0f}s", flush=True)
    out_f.close()
    print(f"score xong: {done} bài -> {args.out} ({failed} batch lỗi)")


def cmd_select(args):
    rows = [json.loads(l) for l in open(args.scored, encoding="utf-8")]
    rows = [r for r in rows if r.get("q_score", 0) >= args.min_q]
    rows.sort(key=lambda r: -r["q_score"])
    sel = rows[:args.total]
    with open(args.out, "w", encoding="utf-8") as f:
        for r in sel:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    qs = [r["q_score"] for r in sel]
    print(f"[{args.scored}] {len(rows)} bài >= {args.min_q}, chọn {len(sel)} "
          f"(q {min(qs) if qs else '-'}..{max(qs) if qs else '-'}) -> {args.out}")


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    p1 = sub.add_parser("scan")
    p1.add_argument("--category", required=True,
                    choices=list(DOMAIN_WORDS))
    p1.add_argument("--raw-root", required=True)
    p1.add_argument("--out", required=True)
    p1.add_argument("--pool", type=int, default=3000)
    p1.add_argument("--min-score", type=float, default=40)
    p1.add_argument("--max-scan", type=int, default=0)
    p1.add_argument("--sub", default=None,
                    help="chỉ lấy bài có labels.level2 này (vd: literature, cuisine)")
    p1.add_argument("--sub-any", default=None,
                    help="danh sách level2 cách nhau dấu phẩy; lấy nếu khớp bất kỳ")
    p1.set_defaults(func=cmd_scan)
    p2 = sub.add_parser("score")
    p2.add_argument("--pool", required=True)
    p2.add_argument("--out", required=True)
    p2.add_argument("--batch", type=int, default=5)
    p2.add_argument("--limit", type=int, default=0)
    p2.add_argument("--shuffle", action="store_true")
    p2.set_defaults(func=cmd_score)
    p3 = sub.add_parser("select")
    p3.add_argument("--scored", required=True)
    p3.add_argument("--out", required=True)
    p3.add_argument("--total", type=int, default=40)
    p3.add_argument("--min-q", type=float, default=7.0)
    p3.set_defaults(func=cmd_select)
    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
