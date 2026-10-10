#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
extract_corpus.py — 从 WanJuan-Vietnamese 原始语料重建本 skill 的足球语料(可选高级工具)

【这不是安装步骤。clone 本 repo 后不会自动运行此脚本,也不需要运行它才能使用 skill。】

skill 写作时只读 references/ 和 examples/(都已在 repo 内),与本脚本无关。
只有当你想要 "重新提炼" 或 "扩展领域" 时,才需要本脚本:

  前置条件(缺一不可):
    1. 你已自行获取 WanJuan-Vietnamese 原始语料(约 303GB,CC BY 4.0,
       来源:上海人工智能实验室 / OpenDataLab)。repo 不含也不分发该语料。
    2. 本机有足够磁盘空间(足球子集约 10GB)。

  用法(三步,全部手动):
    # 1) 先预览能命中多少(不写任何文件)
    python bin/extract_corpus.py --raw /path/to/WanJuan-Vietnamese/raw

    # 2) 确认无误后真提取(写入 10GB 级文件)
    #    注意:必须显式设置 VIET_REBUILD_OK=1,否则即使加了 --yes 也会退回 dry-run
    export VIET_REBUILD_OK=1
    python bin/extract_corpus.py --raw /path/to/.../raw --out ./viet_football --yes

    # 3) 精选范文进 examples/(按体裁分桶,带出处字段)
    python bin/extract_corpus.py --pick ./viet_football/football_corpus.jsonl --examples ./examples/football

安全默认(三重防误运行):
  1. 本脚本不参与安装,repo 无助跑机制会自动调用它。
  2. 不传 --yes 时只统计命中量,dry-run,不写盘。
  3. 即使传了 --yes,若未设 VIET_REBUILD_OK=1,仍会退回 dry-run。

设计要点(相较早期版本的关键修正):
  A. 两级判定:先用「足球专有词」把非足球内容挡在外面(GATE),
     再在其中做「多标签体裁分类」。早前把 tennis / bóng rổ / thể thao /
     vận động viên 等泛指体育词当足球信号,会把网球、篮球稿混入。
  B. 体裁多标签:一篇文章可同时属于 chuyen_nhuong + v_league,不再强行单桶。
  C. 边界样本:命中泛词但未命中专有词的,进 review_needed,不直接成为范文。
  D. 出处字段:每条记录带 source_url / publisher / collected_at / content_sha256 /
     language / sport / genre / review_status / license_or_attribution,缺失显式标 null。
  E. 稳定去重:用全文 SHA-256(规范化后)去重,不再用 hash(c[:300]) 这种跨运行不稳定的方式。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time
import unicodedata
from collections import defaultdict

# ══════════════════════════════════════════════════════════════════════
# 关键词表:分三层,严格程度依次降低
# ══════════════════════════════════════════════════════════════════════

# 1) 足球专有词 —— 命中任一即可确认为足球内容(GATE 通过)
#    只放"只有足球才会用"的词,不放泛指体育词。
FOOTBALL_STRICT = [
    "bóng đá", "quả bóng", "trái bóng", "đội bóng",
    "cầu thủ", "trận đấu", "huấn luyện viên", "hlv ",
    "ghi bàn", "bàn thắng", "thủ môn", "penalty", "phạt góc",
    "việt vị", "thẻ đỏ", "thẻ vàng", "đội tuyển",
    "v-league", "v.league", "world cup", "champions league",
    "europa league", "ngoại hạng anh", "la liga", "serie a",
    "bundesliga", "ligue 1", "asian cup", "aff cup", "sea games",
    "cúp c1", "vòng loại", "vòng chung kết", "hậu vệ", "tiền đạo",
    "tiền vệ", "trọng tài", "sân vận động", "hiệp một", "hiệp hai",
    "hiệp đấu", "sút phạt", "đá phạt", "phạt đền", "luân lưu",
    "cú đúp", "hat-trick", "hattrick", "hiệp phụ", "chấn thương",
    "chuyển nhượng", "bảng đấu", "giải vô địch bóng đá",
    "fifa", "uefa", "afc ", "cfm ", "đt việt nam", "tuyển việt nam",
]
# 注:刻意不含 tennis / bóng rổ / golf / thể thao / vận động viên / olympic /
#    vô địch (泛指)等。这些是其他运动的信号,放入 AMBIGUOUS 走人工核验。

# 2) 弱信号 / 泛指体育词 —— 单独命中不足以判定足球,进 review_needed
AMBIGUOUS = [
    "thể thao", "vận động viên", "olympic", "tỷ số", "cúp quốc gia",
    "giải đấu", "vô địch", "hợp đồng", "clb", "câu lạc bộ",
]

# 3) 反足球信号 —— 命中则直接排除(哪怕同时命中足球词,多半是综合体育页)
NON_FOOTBALL = [
    "bóng rổ", "tennis", "quần vợt", "golf", "bóng chuyền", "bơi lội",
    "điền kinh", "cầu lông", "bóng bàn", "đua xe", "esports",
]

# 廉价预筛词(整行命中任一才 json.loads,省 IO)
PRE = ["bóng", "hlv", "cầu thủ", "trận", "giải", "tuyển", "cúp", "thể thao"]

# ══════════════════════════════════════════════════════════════════════
# 体裁(多标签)。范文按这些桶输出。
# ══════════════════════════════════════════════════════════════════════
GENRES = [
    ("chuyen_nhuong", ["chuyển nhượng", "hợp đồng", "cho mượn", "phí chuyển nhượng",
                        "chiêu mộ", "ký hợp đồng", "mua đứt", "giải phóng hợp đồng"]),
    ("v_league", ["v-league", "v.league", "giải vô địch quốc gia", "cúp quốc gia"]),
    ("doi_tuyen_vn", ["đội tuyển việt nam", "tuyển việt nam", "u23 việt nam",
                       "hlv park", "aff cup", "sea games"]),
    ("world_cup", ["world cup", "vòng loại world cup"]),
    ("champions_league", ["champions league", "cúp c1", "europa league"]),
    ("ngoai_hang", ["ngoại hạng anh", "premier league", "manchester", "chelsea",
                     "arsenal", "liverpool", "tottenham"]),
    ("chau_a", ["asian cup", "vòng chung kết châu á", "vòng loại world cup châu á"]),
    ("phan_tich_chien_thuat", ["chiến thuật", "đội hình", "sơ đồ chiến thuật",
                                "phòng ngự", "tấn công", "pressing"]),
]

BAD = re.compile(
    r"(\.\.\.{3,}|�|\\u[0-9a-f]{4}|quảng cáo|đăng ký nhận tin|click here|http[s]?://|\bads\b"
    r"|bắn cá|đổi thưởng|casino|soi cầu|đánh bài|cá độ|nhà cái|ku casino|fun88|w88|m88"
    r"|tài xỉu online|game bài|lô đề|đăng ký|khuyến mãi|liên hệ quảng cáo|tạp chí doanh nghiệp"
    r"|xem thêm|đọc tiếp|theo dõi|hotline|bài viết liên quan|xem ngay)",
    re.I)
VI_CHARS = "àáảãạăâđêôơưèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ"
MIN_LEN = 100

GUARD_ENV = "VIET_REBUILD_OK"
SCRIPT_VERSION = "2.0.0"

# 数据来源署名(CC BY 4.0 要求)
DATASET_ATTRIBUTION = "WanJuan-Vietnamese, Shanghai AI Laboratory / OpenDataLab, CC BY 4.0"


def norm_text(s: str) -> str:
    """NFC 规范化 + 折叠空白,用于稳定去重。"""
    s = unicodedata.normalize("NFC", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def sha256_text(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8", "replace")).hexdigest()


def classify(text: str, title: str):
    """
    返回 (is_football, genres, confidence, matched)。
      is_football: True=确认为足球;False=非足球;None=边界(需人工核验)
      genres: 命中的体裁列表(多标签)
      confidence: "high"(命中足球专有词) / "review"(仅命中泛词) / "reject"
      matched: 命中的关键词
    """
    low = (title + " " + text).lower()
    if any(k in low for k in NON_FOOTBALL):
        # 但如果同时有强足球词,可能只是综合页面提到别的运动 —— 仍按 review
        if any(k in low for k in FOOTBALL_STRICT):
            return None, [], "review", []
        return False, [], "reject", []
    strict_hits = [k for k in FOOTBALL_STRICT if k in low]
    amb_hits = [k for k in AMBIGUOUS if k in low]
    if not strict_hits:
        if amb_hits:
            return None, [], "review", amb_hits   # 边界:只有泛词
        return False, [], "reject", []
    genres = [g for g, kws in GENRES if any(k in low for k in kws)]
    return True, genres, "high", strict_hits[:12]


def run_extract(raw_dir, out_dir, yes):
    # ── 双重闸门:即使传了 --yes,也必须有显式环境变量才允许写盘 ──
    if yes and os.environ.get(GUARD_ENV) != "1":
        print(f"[已拦截] 检测到 --yes,但未设置环境变量 {GUARD_ENV}=1。")
        print(f"         为防止误运行,本次退回 dry-run(不写盘)。")
        print(f"         确认要真提取,请先执行:export {GUARD_ENV}=1\n")
        yes = False

    files = sorted(glob.glob(os.path.join(raw_dir, "*", "*", "*.jsonl")))
    if not files:
        sys.exit(f"[错误] 在 {raw_dir} 下未找到 */*/*.jsonl。请确认 --raw 指向 WanJuan 的 raw/ 目录。")
    print(f"找到 {len(files)} 个分片")
    print(f"模式:{'提取并写盘' if yes else '预览(dry-run,不写盘)'}")
    print("提示:全量扫描 303GB 可能需要十几分钟到数十分钟,取决于磁盘速度。\n")

    if yes:
        os.makedirs(out_dir, exist_ok=True)
    collected_at = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    out_file = open(os.path.join(out_dir, "football_corpus.jsonl"), "w", encoding="utf-8") if yes else None
    review_file = open(os.path.join(out_dir, "review_needed.jsonl"), "w", encoding="utf-8") if yes else None
    seen, cat_cnt, genre_cnt, total_hit, review_cnt, scanned, rejected = set(), defaultdict(int), defaultdict(int), 0, 0, 0, 0
    t0 = time.time()
    try:
        for fi, fp in enumerate(files, 1):
            cat = "/".join(fp.split("/raw/")[-1].split("/")[:2]) if "/raw/" in fp else os.path.basename(os.path.dirname(fp))
            with open(fp, "r", encoding="utf-8", errors="replace") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    scanned += 1
                    low = line.lower()
                    if not any(p in low for p in PRE):
                        continue
                    try:
                        o = json.loads(line)
                    except Exception:
                        continue
                    c = (o.get("content") or "").strip()
                    if len(c) < MIN_LEN:
                        continue
                    title = (o.get("title") or "").strip()
                    norm_c = norm_text(c)
                    csha = sha256_text(norm_c)
                    if csha in seen:            # 稳定全文去重
                        continue
                    seen.add(csha)
                    is_fb, genres, conf, matched = classify(c, title)
                    if conf == "reject":
                        rejected += 1
                        continue
                    rec = {
                        "id": o.get("id"),
                        "source_url": o.get("url") or o.get("source_url"),
                        "publisher": o.get("publisher") or o.get("source") or None,
                        "published_at": o.get("date") or o.get("published_at"),
                        "collected_at": collected_at,
                        "original_id": o.get("id"),
                        "content_sha256": csha,
                        "language": "vi",
                        "sport": "football" if is_fb else "uncertain",
                        "genre": genres,
                        "review_status": "auto_high" if is_fb else "needs_review",
                        "license_or_attribution": DATASET_ATTRIBUTION,
                        "dataset_category": cat,
                        "title": title[:200],
                        "content": c[:10000],
                        "orig_len": len(c),
                        "matched_keywords": matched[:12],
                    }
                    if is_fb:
                        total_hit += 1
                        cat_cnt[cat] += 1
                        for g in (genres or ["_uncategorized"]):
                            genre_cnt[g] += 1
                        if yes:
                            # excerpt_span 标出范文可用的片段范围(此处默认全文前 1200 字符)
                            rec["excerpt_span"] = [0, min(len(c), 1200)]
                            out_file.write(json.dumps(rec, ensure_ascii=False) + "\n")
                    else:
                        review_cnt += 1
                        if yes:
                            review_file.write(json.dumps(rec, ensure_ascii=False) + "\n")
            if fi % 5 == 0 or fi == len(files):
                print(f"  [{fi}/{len(files)}] 扫描 {scanned} 行,足球 {total_hit} 条,待核验 {review_cnt} 条,排除 {rejected} 条,用时 {time.time()-t0:.0f}s")
    finally:
        if out_file:
            out_file.close()
        if review_file:
            review_file.close()

    print(f"\n完成:{'已写出' if yes else '命中约'} 足球 {total_hit} 条(扫描 {scanned} 行,{time.time()-t0:.0f}s)")
    print(f"  待人工核验(仅命中泛词): {review_cnt} 条")
    print(f"  直接排除(反足球信号): {rejected} 条")
    print("\n按数据集分类:")
    for c, n in sorted(cat_cnt.items(), key=lambda x: -x[1])[:15]:
        print(f"  {c:40s} {n}")
    print("\n按体裁(多标签,可重复计数):")
    for g, n in sorted(genre_cnt.items(), key=lambda x: -x[1]):
        print(f"  {g:28s} {n}")
    if not yes:
        print("\n[预览结束 · 未写任何文件] 确认无误后,加 --yes 真提取。")
    else:
        print(f"\n输出: {out_dir}/football_corpus.jsonl (约 10GB 级)")
        print(f"      {out_dir}/review_needed.jsonl (边界样本,需人工核验后才可入范文)")


def clean_ok(t):
    if BAD.search(t):
        return False
    low = t.lower()
    vi = len(re.findall(f"[{VI_CHARS}]", low))
    alpha = len(re.findall(f"[a-zA-Z{VI_CHARS}]", low))
    if alpha == 0:
        return False
    return vi / max(alpha, 1) > 0.08


def run_pick(src, out_dir, per_theme):
    os.makedirs(out_dir, exist_ok=True)
    picked, seen, scanned = defaultdict(list), set(), 0
    # 只按"主题"体裁选范文(写作体裁 pre_match/analysis/social_post 不单独选范文,
    # 它们复用主题范文 + 各自的规则文件)
    TARGETS = ["chuyen_nhuong", "ngoai_hang", "world_cup", "chau_a",
               "doi_tuyen_vn", "v_league", "champions_league",
               "phan_tich_chien_thuat"]
    # 快速预筛:内容里必须至少出现一个足球硬关键词,才走昂贵的 classify()
    quick_fb = ("bóng đá", "cầu thủ", "trận đấu", "bàn thắng", "đội bóng",
                "huấn luyện viên", "thủ môn", "world cup", "v-league",
                "champions league", "aff cup", "đội tuyển", "ghi bàn",
                "chuyển nhượng", "penalty", "vòng loại")
    with open(src, encoding="utf-8", errors="replace") as f:
        for line in f:
            scanned += 1
            if scanned % 200000 == 0:
                done = sum(1 for t in TARGETS if len(picked[t]) >= per_theme)
                print(f"  ...扫描 {scanned:,} 行, 已满桶 {done}/{len(TARGETS)}", flush=True)
            if all(len(picked[t]) >= per_theme for t in TARGETS):
                print(f"  全部体裁已满 ({scanned:,} 行处停止)", flush=True)
                break
            try:
                r = json.loads(line)
            except Exception:
                continue
            # 快速预筛:内容里必须至少出现一个足球硬关键词,才走昂贵的 classify()
            low_all = ((r.get("title") or "") + " " + (r.get("content") or "")[:2000]).lower()
            if not any(k in low_all for k in quick_fb):
                continue
            # 优先用记录里已有的判定;老记录缺字段时现场重判
            rs = r.get("review_status")
            if rs == "needs_review":
                continue
            if rs is None or r.get("sport") not in ("football", "uncertain"):
                # 老格式记录:现场 classify() 一次,确保足球正确
                is_fb, genres2, conf, matched2 = classify(r.get("content", ""), r.get("title", ""))
                if conf != "high":
                    continue
                r = dict(r)
                r["sport"] = "football"
                r["genre"] = genres2
                r["review_status"] = "auto_high"
                r["content_sha256"] = r.get("content_sha256") or sha256_text(norm_text(r.get("content", "")))
            L = r.get("orig_len", 0)
            if L < 800 or L > 4500:
                continue
            c = r.get("content", "")
            if not clean_ok(c):
                continue
            title = (r.get("title") or "").strip()
            if len(title) < 10 or not clean_ok(title):
                continue
            folded = norm_text(c)
            csha = r.get("content_sha256") or sha256_text(folded)
            if csha in seen:
                continue
            genres = r.get("genre") or []
            if not genres:
                continue
            # 出处字段:WanJuan 为清洗后的文本语料,不含网页 URL/发布者/发布时间。
            # 不可得的一律显式标 "unavailable"（而非留空或编造），来源链止于数据集本身。
            MISS = "unavailable"
            # 多标签:一篇文章可进多个体裁桶(但每桶上限 per_theme)
            placed = False
            for g in genres:
                if len(picked[g]) < per_theme:
                    picked[g].append({
                        "id": r.get("id"),
                        "theme": g,
                        "title": title[:200],
                        "content": c[:4500],
                        "len": L,
                        "source_url": r.get("source_url") or MISS,
                        "publisher": r.get("publisher") or MISS,
                        "published_at": r.get("published_at") or MISS,
                        "collected_at": r.get("collected_at") or MISS,
                        "original_id": r.get("id"),
                        "source_dataset": "WanJuan-Vietnamese",
                        "content_sha256": csha,
                        "language": "vi",
                        "sport": "football",
                        "genre": g,
                        "review_status": "auto_high",
                        "license_or_attribution": r.get("license_or_attribution")
                        or "WanJuan-Vietnamese (Shanghai AI Laboratory, OpenDataLab) — CC BY 4.0",
                    })
                    placed = True
            if placed:
                seen.add(csha)
    total = 0
    for theme in picked:
        with open(os.path.join(out_dir, f"{theme}.jsonl"), "w", encoding="utf-8") as f:
            for rec in picked[theme]:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        total += len(picked[theme])
        print(f"  {theme:28s} {len(picked[theme])}")
    print(f"\n精选 {total} 条范文 -> {out_dir}/ (均带出处字段)")


def main():
    ap = argparse.ArgumentParser(description="从 WanJuan-Vietnamese 原始语料重建足球语料(可选高级工具,不参与 skill 安装)")
    ap.add_argument("--raw", help="WanJuan 原始语料 raw/ 目录(提取模式)")
    ap.add_argument("--out", default="./viet_football", help="提取输出目录(默认 ./viet_football)")
    ap.add_argument("--yes", action="store_true", help="确认真提取并写盘(还需环境变量 VIET_REBUILD_OK=1,否则退回 dry-run)")
    ap.add_argument("--pick", help="范文精选:输入的 football_corpus.jsonl(精选模式)")
    ap.add_argument("--examples", default="./examples/football", help="范文输出目录(默认 ./examples/football)")
    ap.add_argument("--per-theme", type=int, default=20, help="每体裁精选条数(默认 20)")
    a = ap.parse_args()
    if a.pick:
        run_pick(a.pick, a.examples, a.per_theme)
    elif a.raw:
        run_extract(a.raw, a.out, a.yes)
    else:
        ap.print_help()
        print("\n[提醒] 本脚本是可选工具,skill 使用不需要它。参见 README 的「高级:重建语料」。")


if __name__ == "__main__":
    main()
