#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_review.py — 把用户填好的确认表回写。

评审要求:
  - type_reviewed=True 只能在**用户确认之后**写入,并记录 reviewed_by=human
  - 本脚本只读用户填好的 CSV,不改任何未确认项

用法:
    python bin/apply_review.py --sheet distill_football/确认表_候选范文.csv
    python bin/apply_review.py --sheet ... --dry-run   # 只看会改什么

CSV 约定:
  - "用户结论" 列: 填 '可用'/'是'/'yes'/'1' → 视为确认通过
                   填 '不可用'/'否'/'no'/'0' → 视为否决
                   留空 → 跳过(未确认)
"""
import argparse
import csv
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "distill_football"

YES = {"可用", "是", "yes", "y", "1", "true", "通过", "ok"}
NO = {"不可用", "否", "no", "n", "0", "false", "不通过"}


def read_sheet(path):
    """返回 {id: (verdict, note)}。"""
    out = {}
    with open(path, newline="", encoding="utf-8-sig") as f:
        rd = csv.DictReader(f)
        for row in rd:
            # 找结论列(容忍列名差异)
            verdict = ""
            note = ""
            for k, v in row.items():
                if not k:
                    continue
                if "用户结论" in k or "结论" in k:
                    verdict = (v or "").strip()
                if "备注" in k:
                    note = (v or "").strip()
            rid = (row.get("ID") or "").strip()
            if rid and verdict:
                out[rid] = (verdict.lower(), note)
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    sheet = Path(args.sheet)
    if not sheet.is_absolute():
        sheet = ROOT / sheet
    if not sheet.exists():
        print(f"ERROR: 找不到确认表 {sheet}", file=sys.stderr)
        return 1

    verdicts = read_sheet(sheet)
    confirmed = {k: v for k, v in verdicts.items() if v[0] in YES}
    rejected = {k: v for k, v in verdicts.items() if v[0] in NO}
    print(f"确认表读入 {len(verdicts)} 行:通过 {len(confirmed)},否决 {len(rejected)}")

    # 回写到 candidates.jsonl(候选范文池)
    # 注意:不写入 distill_football/*.jsonl(那些是统计口径),而是单独写入
    #       references/examples_football/ (经确认的范文)
    candidates = DIST / "candidates.jsonl"
    if not candidates.exists():
        print("ERROR: 还没有 candidates.jsonl(需先跑 select_candidates.py)",
              file=sys.stderr)
        return 1

    recs = [json.loads(l) for l in candidates.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    n_ok = 0
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for r in recs:
        v = confirmed.get(r.get("id"))
        if v:
            r["type_reviewed"] = True
            r["reviewed_by"] = "human"
            r["reviewed_at"] = stamp
            if v[1]:
                r["review_note"] = v[1]
            n_ok += 1
        elif r.get("type_reviewed") is None:
            # 保持未确认状态(不臆造)
            r["type_reviewed"] = False

    print(f"标记 type_reviewed=True 的候选: {n_ok} 条")
    if args.dry_run:
        print("(--dry-run,未写盘)")
        return 0

    outdir = ROOT / "references" / "examples_football"
    outdir.mkdir(parents=True, exist_ok=True)
    with (outdir / "reviewed.jsonl").open("w", encoding="utf-8") as f:
        for r in recs:
            if r.get("type_reviewed") is True:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
    candidates.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in recs) + "\n",
        encoding="utf-8")
    print(f"→ {outdir}/reviewed.jsonl (仅人工确认过的范文)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
