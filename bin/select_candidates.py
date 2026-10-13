#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""select_candidates.py — 从抽取结果挑选候选范文(待人工确认)。

规则(评审):
  - 赛果/赛前/社交三类,各 30 条
  - 只取 year >= 2023
  - 越南本土和欧洲大约各占一半
  - 社交类凑不够 30 条就多少给多少,并在报告写明
  - 输出 candidates.jsonl:type_reviewed=False,带 year 字段

用法:
    python bin/select_candidates.py [--n 30] [--out distill_football/candidates.jsonl]
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "distill_football"

EU_RE = re.compile(r"Ngoại hạng Anh|Champions League|La Liga|Serie A|Bundesliga|"
                   r"Ligue 1|Premier League|World Cup|Euro|Braga|Sporting|"
                   r"Real Madrid|Barcelona|MU|Man Utd|Liverpool|Arsenal|Chelsea", re.I)
VN_RE = re.compile(r"V\.?League|đội tuyển Việt Nam|tuyển Việt Nam|VFF|Hà Nội FC|"
                   r"Hoàng Anh Gia Lai|SLNA|Thanh Hóa|Hải Phòng|Sài Gòn|"
                   r"Đà Nẵng|Bình Dương|Nam Định|Thể Công", re.I)


def load(cat):
    f = DIST / f"{cat}.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


def region(r):
    h = r.get("head", "")
    if VN_RE.search(h):
        return "vn"
    if EU_RE.search(h):
        return "eu"
    return "other"


def pick_half(recs, n, seed):
    """越南/欧洲各半(不足的用 other 补)。"""
    random.seed(seed)
    vn = [r for r in recs if region(r) == "vn"]
    eu = [r for r in recs if region(r) == "eu"]
    ot = [r for r in recs if region(r) == "other"]
    random.shuffle(vn), random.shuffle(eu), random.shuffle(ot)
    half = n // 2
    out = vn[:half] + eu[:n - len(vn[:half])]
    if len(out) < n:
        out += ot[:n - len(out)]
    if len(out) < n:
        out += [r for r in vn[half:] + eu[half:] if r not in out][:n - len(out)]
    return out[:n]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="distill_football/candidates.jsonl")
    args = ap.parse_args(argv)

    out = []
    report = []
    for cat in ["ket_qua", "truoc_tran", "social"]:
        recs = [r for r in load(cat) if (r.get("year") or 0) >= 2023]
        pick = pick_half(recs, args.n, args.seed)
        for r in pick:
            r = dict(r)
            r["candidate_type"] = cat
            r["type_reviewed"] = False      # 未确认(等人工)
            out.append(r)
        n_vn = sum(1 for r in pick if region(r) == "vn")
        n_eu = sum(1 for r in pick if region(r) == "eu")
        report.append(f"  {cat:12s}: 2023+ 池 {len(recs):5,} → 选 {len(pick):3d} "
                      f"(越南 {n_vn} / 欧洲 {n_eu})")

    print("候选范文:")
    print("\n".join(report))
    outp = ROOT / args.out
    with outp.open("w", encoding="utf-8") as f:
        for r in out:
            rr = {k: v for k, v in r.items() if k != "sig"}
            f.write(json.dumps(rr, ensure_ascii=False) + "\n")
    print(f"\n共 {len(out)} 条 → {outp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
