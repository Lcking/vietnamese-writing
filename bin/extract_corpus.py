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

    # 3) 精选范文进 examples/(按主题分桶)
    python bin/extract_corpus.py --pick ./viet_football/football_corpus.jsonl --examples ./examples/football

安全默认(三重防误运行):
  1. 本脚本不参与安装,repo 无助跑机制会自动调用它。
  2. 不传 --yes 时只统计命中量,dry-run,不写盘。
  3. 即使传了 --yes,若未设 VIET_REBUILD_OK=1,仍会退回 dry-run。
"""
import argparse
import glob
import hashlib
import json
import os
import re
import sys
import time
from collections import defaultdict

# ── 精确关键词(避免 hiệp / bóng 单独误命中)──
PRECISE = [
    "bóng đá", "quả bóng", "trái bóng", "đội bóng", "cầu thủ",
    "trận đấu", "huấn luyện viên", "hlv ", "ghi bàn", "bàn thắng",
    "thủ môn", "world cup", "v-league", "giải vô địch bóng đá",
    "penalty", "phạt góc", "việt vị", "thẻ đỏ", "thẻ vàng",
    "champions league", "europa league", "đội tuyển", "tỷ số",
    "sân vận động", "hiệp một", "hiệp hai", "hiệp đấu",
    "vòng loại", "vòng chung kết", "cúp quốc gia", "sea games",
    "uefa", "fifa", "bóng đá việt nam", "đội tuyển việt nam",
    "sút phạt", "đá phạt", "chấn thương", "chuyển nhượng",
    "hậu vệ", "tiền đạo", "tiền vệ", "trọng tài", "bảng đấu",
    "afc", "aff cup", "cúp c1", "ngoại hạng anh", "la liga",
    "serie a", "bundesliga", "ligue 1", "manchester", "real madrid",
    "barcelona", "psg", "juventus", "bayern", "bóng rổ", "tennis",
    "thể thao", "vận động viên", "olympic", "hlv trưởng",
]
# 廉价预筛词(整行命中任一才 json.loads,省 IO)
PRE = ["bóng", "thể thao", "hlv", "cầu thủ", "world cup", "trận", "giải"]

# ── 范文主题分桶 ──
THEMES = [
    ("doi_tuyen_vn", ["đội tuyển việt nam", "tuyển việt nam", "u23 việt nam", "hlv park", "aff cup", "sea games"]),
    ("world_cup", ["world cup", "vòng loại world cup"]),
    ("ngoai_hang", ["ngoại hạng anh", "premier league", "manchester", "chelsea", "arsenal", "liverpool"]),
    ("champions_league", ["champions league", "cúp c1", "europa league"]),
    ("chuyen_nhuong", ["chuyển nhượng", "hợp đồng", "cho mượn", "phí chuyển nhượng"]),
    ("v_league", ["v-league", "v.league", "cúp quốc gia", "giải vô địch quốc gia"]),
    ("chau_a", ["asian cup", "vòng chung kết châu á", "afc", "vòng loại world cup châu á"]),
    ("phan_tich_chien_thuat", ["chiến thuật", "đội hình", "sơ đồ", "phòng ngự", "tấn công"]),
]
BAD = re.compile(r"(\.\.\.{3,}|�|\\u[0-9a-f]{4}|quảng cáo|đăng ký|click|http[s]?://|\bads\b)", re.I)
VI_CHARS = "àáảãạăâđêôơưèéẻẽẹìíỉĩịòóỏõọùúủũụỳýỷỹỵ"
MIN_LEN = 100


def is_football(text):
    t = text.lower()
    return [k for k in PRECISE if k in t]


GUARD_ENV = "VIET_REBUILD_OK"


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
    out_file = open(os.path.join(out_dir, "football_corpus.jsonl"), "w", encoding="utf-8") if yes else None
    seen, cat_cnt, total_hit, scanned = set(), defaultdict(int), 0, 0
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
                    title = o.get("title") or ""
                    hits = is_football(title + " " + c)
                    if not hits:
                        continue
                    h = hashlib.md5(c.encode("utf-8", "replace")).hexdigest()
                    if h in seen:
                        continue
                    seen.add(h)
                    total_hit += 1
                    cat_cnt[cat] += 1
                    if yes:
                        out_file.write(json.dumps({
                            "id": o.get("id"), "category": cat, "title": title[:200],
                            "content": c[:10000], "orig_len": len(c), "hits": hits[:8],
                        }, ensure_ascii=False) + "\n")
            if fi % 5 == 0 or fi == len(files):
                print(f"  [{fi}/{len(files)}] 扫描 {scanned} 行,命中 {total_hit} 条,用时 {time.time()-t0:.0f}s")
    finally:
        if out_file:
            out_file.close()

    print(f"\n完成:{'已写出' if yes else '命中约'} {total_hit} 条(扫描 {scanned} 行,{time.time()-t0:.0f}s)")
    for c, n in sorted(cat_cnt.items(), key=lambda x: -x[1])[:15]:
        print(f"  {c:40s} {n}")
    if not yes:
        print("\n[预览结束 · 未写任何文件] 确认无误后,加 --yes 真提取。")
    else:
        print(f"\n输出: {os.path.join(out_dir, 'football_corpus.jsonl')}(约 10GB 级)")


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
    with open(src, encoding="utf-8", errors="replace") as f:
        for line in f:
            scanned += 1
            try:
                r = json.loads(line)
            except Exception:
                continue
            L = r.get("orig_len", 0)
            if L < 800 or L > 4500:
                continue
            c = r.get("content", "")
            if not clean_ok(c):
                continue
            title = (r.get("title") or "").strip()
            if len(title) < 10:
                continue
            low = (title + " " + c).lower()
            for theme, kws in THEMES:
                if any(k in low for k in kws):
                    h = hash(c[:300])
                    if h in seen or len(picked[theme]) >= per_theme:
                        break
                    seen.add(h)
                    picked[theme].append({"theme": theme, "title": title[:200], "content": c[:4500], "len": L})
                    break
    total = 0
    for theme in picked:
        with open(os.path.join(out_dir, f"{theme}.jsonl"), "w", encoding="utf-8") as f:
            for rec in picked[theme]:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        total += len(picked[theme])
        print(f"  {theme:28s} {len(picked[theme])}")
    print(f"\n精选 {total} 条范文 -> {out_dir}/")


def main():
    ap = argparse.ArgumentParser(description="从 WanJuan-Vietnamese 原始语料重建足球语料(可选高级工具,不参与 skill 安装)")
    ap.add_argument("--raw", help="WanJuan 原始语料 raw/ 目录(提取模式)")
    ap.add_argument("--out", default="./viet_football", help="提取输出目录(默认 ./viet_football)")
    ap.add_argument("--yes", action="store_true", help="确认真提取并写盘(还需环境变量 VIET_REBUILD_OK=1,否则退回 dry-run)")
    ap.add_argument("--pick", help="范文精选:输入的 football_corpus.jsonl(精选模式)")
    ap.add_argument("--examples", default="./examples/football", help="范文输出目录(默认 ./examples/football)")
    ap.add_argument("--per-theme", type=int, default=20, help="每主题精选条数(默认 20)")
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
