#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_review_ket_qua.py — 生成赛果抽查确认表(评审要求)。

按 ket_qua_score 分层抽 50 条:高分 20 + 中分 20 + 低分 10。
字段: ID / 年份 / 排序分 / 正文前300字符 / 百晓生建议标签 / 理由 / 用户结论(空)

含正文,不进仓库。
"""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import extract_football as ef  # noqa: E402


def load_kq():
    recs = []
    for fp in sorted(ef.FULLDIR.glob("*.jsonl")):
        for line in fp.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            d = json.loads(line)
            if "ket_qua" in d.get("tags", []):
                recs.append(d)
    return recs


def suggest(t):
    """给出仅供参照的建议标签(用户结论须本人填)。"""
    head = t[:400]
    if ef.is_betting(t):
        return "非赛果", "含博彩词(应已被隔离,若出现说明词表需补)"
    for rx, lab, why in [
        (r"HLV|huấn luyện viên|chấn thương|đội hình ra sân", "非赛果", "主帅/伤病/阵容新闻"),
        (r"nhận định|trước trận|sẽ gặp|dự đoán", "赛前", "偏赛前预告"),
        (r"chuyển nhượng|ký hợp đồng|gia nhập", "非赛果", "转会新闻"),
    ]:
        import re
        if re.search(rx, head, re.I):
            return lab, why
    return "赛果", "首段有比分/结果动词,含进球分钟"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="distill_football/review_ket_qua_50.csv")
    ap.add_argument("--n", type=int, default=50)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    recs = load_kq()
    if not recs:
        print("ERROR: 没有赛果全文,先跑抽取", file=sys.stderr)
        return 1
    for r in recs:
        r["_score"] = ef.ket_qua_score(r["text"])
    recs.sort(key=lambda r: -r["_score"])
    n = len(recs)
    # 分层:高 20 / 中 20 / 低 10
    hi = recs[:n // 3]
    mid = recs[n // 3: 2 * n // 3]
    lo = recs[2 * n // 3:]
    random.seed(args.seed)
    pick = (random.sample(hi, min(20, len(hi)))
            + random.sample(mid, min(20, len(mid)))
            + random.sample(lo, min(10, len(lo))))
    random.shuffle(pick)
    pick = pick[:args.n]

    outp = ROOT / args.out
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(["编号", "ID", "年份", "排序分", "正文前300字符",
                    "百晓生建议标签", "建议理由", "用户结论(赛果/非赛果)", "用户备注"])
        for i, r in enumerate(pick, 1):
            lab, why = suggest(r["text"])
            w.writerow([f"K{i:02d}", r["id"], r.get("year") or "", r["_score"],
                        r["text"][:300].replace("\n", " "), lab, why, "", ""])
    print(f"确认表 {len(pick)} 条 → {outp}")
    from collections import Counter
    print("分层得分分布:", Counter(r["_score"] for r in pick))
    return 0


if __name__ == "__main__":
    sys.exit(main())
