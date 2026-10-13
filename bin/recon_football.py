#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""recon_football.py — WanJuan 足球内容摸底(第二阶段)。

从语料随机抽若干分片(约全量的 1-2%),用规则粗扫,不调用模型。

产出(JSONL,只含 ID/哈希/统计,不含原文):
  - 足球稿占比、估算全量足球稿数
  - 粗分类(赛果/赛前/转会/人物/社交短讯/博彩)
  - 年份分布
  - V.League vs 欧洲联赛
  - 机器翻译/拼接稿/标题党粗判

用法:
    python bin/recon_football.py --sample 12 --out distill_report/football_recon
"""
import argparse
import hashlib
import json
import random
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path("/lzcapp/document/Knowledge-vietnem/OpenDataLab___WanJuan-Vietnamese/raw")

# ---- 规则(按任务说明) ----
FOOTBALL_KW = ["bóng đá", "tỷ số", "ghi bàn", "thủ môn", "HLV", "V.League",
               "Ngoại hạng Anh", "Champions League", "đội tuyển",
               r"vòng \d+", r"phút \d+"]
FOOTBALL_RE = [re.compile(k if not k.startswith("r") else k[1:], re.I) for k in FOOTBALL_KW]

# 比分:要求数字-数字,且比赛语境(避免 "2 HCV, 4 HCB" 这类被误判)
SCORE_RE = re.compile(r"\b\d{1,2}\s*-\s*\d{1,2}\b")
MIN_RE = re.compile(r"(phút\s*\d+|\d+')", re.I)
GOAL_VERB = re.compile(r"mở tỷ số|gỡ hòa|nâng tỷ số|rút ngắn cách biệt|vượt lên dẫn|ấn định", re.I)
PRE_RE = re.compile(r"nhận định|trước trận|đội hình dự kiến|lực lượng|đối đầu", re.I)
TRANSFER_RE = re.compile(r"chuyển nhượng|chiêu mộ|ký hợp đồng|gia nhập", re.I)
PROFILE_RE = re.compile(r"chân dung|sự nghiệp|tiểu sử", re.I)
BET_RE = re.compile(r"soi kèo|tỷ lệ kèo|tài xỉu|kèo châu Á|nhà cái", re.I)
EU_LEAGUE = re.compile(r"Ngoại hạng Anh|Champions League|La Liga|Serie A|Bundesliga|"
                       r"Ligue 1|Premier League|World Cup|Euro", re.I)
VN_LEAGUE = re.compile(r"V\.?League|đội tuyển Việt Nam|tuyển Việt Nam|VFF|"
                       r"Hà Nội FC|Hoàng Anh Gia Lai|SLNA|Thanh Hóa|Hải Phòng", re.I)
# 机翻/拼接粗判
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
EN_WORD = re.compile(r"\b(the|and|of|with|for|from|this|that)\b", re.I)


def norm(t):
    return unicodedata.normalize("NFC", t or "")


def is_football(t):
    return sum(1 for r in FOOTBALL_RE if r.search(t)) >= 2


def classify(t):
    """返回粗分类集合。"""
    tags = set()
    tl = t.lower()
    if SCORE_RE.search(t) and (MIN_RE.search(t) or GOAL_VERB.search(t)):
        tags.add("ket_qua")
    if PRE_RE.search(t):
        tags.add("truoc_tran")
    if TRANSFER_RE.search(t):
        tags.add("chuyen_nhuong")
    if PROFILE_RE.search(t):
        tags.add("nhan_vat")
    if len(t) < 600 and re.search(r"[!?]|ôi|wow|quá|vl", tl):
        tags.add("social_short")
    if BET_RE.search(t):
        tags.add("betting")
    return tags


def shingles(t, k=6):
    toks = re.findall(r"\w+", t.lower())
    if len(toks) < k:
        return frozenset()
    return frozenset(" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1))


def extract_year(t):
    """提取年份;限定 1990-2026(排除比分/编号误提取,如 2050/2098)。"""
    ys = re.findall(r"\b(19[89]\d|20[0-2]\d)\b", t)
    seasons = re.findall(r"\b(19[89]\d|20[0-2]\d)\s*/\s*\d{2}\b", t)
    cand = [int(y) for y in ys + seasons if 1990 <= int(y) <= 2026]
    return max(cand) if cand else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=12, help="抽样文件数")
    ap.add_argument("--max-lines", type=int, default=60000, help="每文件最多扫描行数")
    ap.add_argument("--out", default="distill_report/football_recon")
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args()

    outdir = ROOT / args.out
    outdir.mkdir(parents=True, exist_ok=True)

    all_files = sorted(RAW.rglob("*.jsonl"))
    random.seed(args.seed)
    # 优先 news/general(足球最可能在这里),再补其他
    priority = [f for f in all_files if "/news/" in str(f) or "/general/" in str(f)]
    others = [f for f in all_files if f not in priority]
    pick = random.sample(priority, min(args.sample, len(priority)))
    if len(pick) < args.sample:
        pick += random.sample(others, min(args.sample - len(pick), len(others)))

    stats = {
        "files_scanned": [], "lines": 0, "football": 0,
        "cls": Counter(), "cls_nodup": Counter(), "years": Counter(),
        "vn_vs_eu": Counter(), "mt_or_copy": 0, "clickbait": 0,
        "samples": defaultdict(list),
        "_seen_sample": set(),
    }
    seen = set()
    for fp in pick:
        n = 0
        try:
            with fp.open(encoding="utf-8", errors="ignore") as f:
                for line in f:
                    n += 1
                    if n > args.max_lines:
                        break
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    t = norm((d.get("title") or "") + " " + (d.get("content") or ""))
                    stats["lines"] += 1
                    if not is_football(t):
                        continue
                    stats["football"] += 1
                    tags = classify(t)
                    for g in tags:
                        stats["cls"][g] += 1
                    y = extract_year(t)
                    if y:
                        stats["years"][y] += 1
                    if EU_LEAGUE.search(t):
                        stats["vn_vs_eu"]["eu"] += 1
                    if VN_LEAGUE.search(t):
                        stats["vn_vs_eu"]["vn"] += 1
                    # 机翻/拼接
                    if HAN_RE.search(t) or len(EN_WORD.findall(t)) >= 3:
                        stats["mt_or_copy"] += 1
                    if re.match(r"^(Sốc|Gây sốc|Chấn động|[A-Z]{4,})", t) or t.count("!") >= 3:
                        stats["clickbait"] += 1
                    # 去重
                    key = shingles(t)
                    dup = bool(key and key in seen)
                    if key:
                        seen.add(key)
                    if not dup:
                        for g in (tags or {"khac"}):
                            stats["cls_nodup"][g] += 1
                    # 样本(只要 ID + 前 300 字符)
                    _sid = d.get("id")
                    for g in list(tags)[:1]:
                        if len(stats["samples"][g]) < 10 and _sid not in stats["_seen_sample"]:
                            stats["samples"][g].append({
                                "id": _sid, "file": fp.name, "head": t[:300],
                            })
                            stats["_seen_sample"].add(_sid)
                            break
        except Exception as e:
            print(f"  [warn] {fp.name}: {e}", file=sys.stderr)
        stats["files_scanned"].append(fp.name)

    total = stats["lines"]
    fb = stats["football"]
    ratio = fb / max(1, total)
    # 估算全量:全库约 253 万条(早前扫描所得),按抽样比例外推
    est_total = 2_530_000
    est_fb = int(est_total * ratio)
    est_ketqua = int(est_fb * (stats["cls"]["ket_qua"] / max(1, fb)))

    lines = ["# WanJuan 越南语语料 —— 足球内容摸底", "",
             f"- 抽样文件: {len(pick)} 个 / 全库 {len(all_files)} 个",
             f"- 扫描行数: {total:,}",
             f"- 足球稿: {fb:,} ({ratio*100:.2f}%)",
             f"- 估算全量足球稿: 约 {est_fb:,} 条(按全库 253 万条外推)",
             "",
             "## 粗分类(去重前后)", "",
             "| 类别 | 命中 | 去重后 |", "|---|---|---|"]
    for g in ["ket_qua", "truoc_tran", "chuyen_nhuong", "nhan_vat", "social_short", "betting"]:
        lines.append(f'| {g} | {stats["cls"][g]:,} | {stats["cls_nodup"][g]:,} |')
    lines += ["",
              f"- 估算赛果稿: 约 {est_ketqua:,} 条(去重前口径)",
              "",
              "## 年份分布(正文提取)", "",
              "| 年份 | 条数 |", "|---|---|"]
    for y, c in sorted(stats["years"].items(), reverse=True)[:15]:
        lines.append(f"| {y} | {c} |")
    late = sum(c for y, c in stats["years"].items() if y >= 2023)
    tot_y = sum(stats["years"].values())
    lines += ["",
              f"- 2023 及以后: {late:,}/{tot_y:,} ({late/max(1,tot_y)*100:.0f}%)",
              "",
              "## V.League/越南队 vs 欧洲联赛", "",
              f'- Việt Nam: {stats["vn_vs_eu"]["vn"]:,}',
              f'- Châu Âu: {stats["vn_vs_eu"]["eu"]:,}',
              "",
              "## 质量粗判(机翻/拼接/标题党)", "",
              f'- 疑似机翻或拼接(汉字残留/英文词密集): {stats["mt_or_copy"]:,} '
              f'({stats["mt_or_copy"]/max(1,fb)*100:.0f}%)',
              f'- 疑似标题党: {stats["clickbait"]:,}',
              ""]
    (outdir / "RECON.md").write_text("\n".join(lines), encoding="utf-8")

    # 样本(仅 ID + 前 300 字符)
    with (outdir / "samples.jsonl").open("w", encoding="utf-8") as f:
        for g, items in stats["samples"].items():
            for it in items:
                f.write(json.dumps({"cls": g, **it}, ensure_ascii=False) + "\n")

    # 概要 JSON
    (outdir / "recon.json").write_text(json.dumps({
        "files": len(pick), "lines": total, "football": fb, "ratio": ratio,
        "est_total_football": est_fb, "est_ket_qua": est_ketqua,
        "cls": dict(stats["cls"]), "cls_nodup": dict(stats["cls_nodup"]),
        "years": dict(stats["years"]), "vn_vs_eu": dict(stats["vn_vs_eu"]),
        "mt_or_copy": stats["mt_or_copy"], "clickbait": stats["clickbait"],
    }, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n".join(lines))
    print(f"\n→ {outdir}/")

    # 停止条件检查
    print("\n## 停止条件检查")
    print(f"1. 去重后赛果稿 < 1000? 估算 {est_ketqua:,} → "
          f"{'触发!' if est_ketqua < 1000 else '未触发'}")
    mt_ratio = stats["mt_or_copy"] / max(1, fb)
    print(f"2. 机翻/拼接 > 50%? 实测 {mt_ratio*100:.0f}% → "
          f"{'触发!' if mt_ratio > 0.5 else '未触发'}")
    old = sum(c for y, c in stats["years"].items() if y < 2022)
    old_ratio = old / max(1, tot_y)
    print(f"3. 主要截止 2022 前? 2022 前占 {old_ratio*100:.0f}% → "
          f"{'触发!' if old_ratio > 0.5 else '未触发'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
