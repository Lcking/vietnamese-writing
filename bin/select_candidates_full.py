#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""select_candidates_full.py — 从全量抽取结果选候选范文(待人工确认)。

规则(评审确认):
  - 赛果 / 赛前 / 社交 三类,各 30 条
  - 只取 year >= 2023(2023+ 有 5.8 万赛果,不必放宽到 2021)
  - 越南本土和欧洲大约各占一半
  - 社交类凑不够 30 条 → 有多少给多少,报告写明实际数量
  - 赛果类只从 **Qwen 判定为真赛果** 的里面选
  - 输出 candidates.jsonl: type_reviewed=False, 带 year

用法:
    python bin/select_candidates_full.py --n 30 --year-from 2023
"""
import argparse
import json
import random
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import extract_football as ef  # noqa: E402

EU_RE = re.compile(
    r"Ngoại hạng Anh|Champions League|La Liga|Serie A|Bundesliga|Ligue 1|"
    r"Premier League|World Cup|Euro|Braga|Sporting|Real Madrid|Barcelona|"
    r"Man Utd|Manchester|Liverpool|Arsenal|Chelsea|Bayern|Juventus|PSG|"
    r"Tottenham|Milan|Inter|Napoli|Dortmund|Ajax", re.I)
VN_RE = re.compile(
    r"V\.?League|đội tuyển Việt Nam|tuyển Việt Nam|VFF|Hà Nội FC|"
    r"Hoàng Anh Gia Lai|HAGL|SLNA|Sông Lam|Thanh Hóa|Hải Phòng|Sài Gòn|"
    r"Đà Nẵng|Bình Dương|Nam Định|Thể Công|Viettel|Bình Định|"
    r"Than Quảng Ninh|SHB|TPHCM|TP\.? HCM|Quảng Nam|Huế|Long An|"
    r"Cần Thơ|Đồng Nai|Khánh Hòa|Phố Hiến|Bà Rịa", re.I)


def region(t):
    if VN_RE.search(t):
        return "vn"
    if EU_RE.search(t):
        return "eu"
    return "other"


def pick_half(recs, n, seed):
    """越南/欧洲各半,不足用 other 补。"""
    rnd = random.Random(seed)
    vn = [r for r in recs if region(r["text"]) == "vn"]
    eu = [r for r in recs if region(r["text"]) == "eu"]
    ot = [r for r in recs if region(r["text"]) == "other"]
    for x in (vn, eu, ot):
        rnd.shuffle(x)
    half = n // 2
    out = vn[:half]
    need = n - len(out)
    out += eu[:need]
    if len(out) < n:
        out += ot[:n - len(out)]
    if len(out) < n:
        rest = [r for r in vn[half:] + eu[need:] if r not in out]
        out += rest[:n - len(out)]
    return out[:n]


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=30)
    ap.add_argument("--year-from", type=int, default=2023)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", default="distill_football/candidates_full.jsonl")
    args = ap.parse_args(argv)

    # Qwen 判为真赛果的 id
    judged = ROOT / "distill_football" / "ket_qua_full_judged.jsonl"
    kq_ok = set()
    if judged.exists():
        for l in judged.read_text(encoding="utf-8").splitlines():
            if not l.strip():
                continue
            d = json.loads(l)
            if d.get("is_match_report") is True:
                kq_ok.add(d["id"])
    print(f"Qwen 判为真赛果: {len(kq_ok)}")

    # 收集候选
    pools = {"ket_qua": [], "truoc_tran": [], "social": []}
    for fp in sorted(ef.FULLDIR.glob("*.jsonl")):
        with fp.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                y = r.get("year")
                if not y or y < args.year_from:
                    continue
                tags = r.get("tags", [])
                t = r.get("text", "")
                if ef.is_aggregator(t) or ef.OTHER_SPORT_TEAMS.search(t):
                    continue
                if ef.EF_OFFTOPIC_RE.search(t[:600]):
                    continue
                for cat in pools:
                    if cat in tags:
                        if cat == "ket_qua" and r.get("id") not in kq_ok:
                            continue
                        pools[cat].append({"id": r["id"], "year": y,
                                           "text": t,
                                           "content_hash": r.get("content_hash", "")})
    out, report = [], []
    for cat in ["ket_qua", "truoc_tran", "social"]:
        pool = pools[cat]
        pick = pick_half(pool, args.n, args.seed + hash(cat) % 1000)
        for r in pick:
            out.append({**{k: v for k, v in r.items() if k != "text"},
                        "candidate_type": cat, "type_reviewed": False,
                        "head": r["text"][:300]})
        n_vn = sum(1 for r in pick if region(r["text"]) == "vn")
        n_eu = sum(1 for r in pick if region(r["text"]) == "eu")
        report.append(f"  {cat:12s}: 池 {len(pool):>7,} → 选 {len(pick):3d} "
                      f"(越南 {n_vn} / 欧洲 {n_eu})")

    print("候选范文:")
    print("\n".join(report))
    outp = ROOT / args.out
    with outp.open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\n共 {len(out)} 条 → {outp}")
    # 社交类不足时写明
    if len(pools["social"]) < args.n:
        print(f"注：社交短帖池仅 {len(pools['social'])} 条"
              f"（{args.year_from}+），不足 {args.n}，按实际数量给出。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
