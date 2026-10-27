#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""apply_human_reviews.py — 把导师确认结果写回候选范文池。

规则(用户亲定):
  - type_reviewed=True 只能由**用户/导师**确认后写入,记 reviewed_by=human
  - 只有 answer=='ok' 的才标记;被拒的剔除
  - 从 distill_football/candidates_full.jsonl 建 references/examples_football/

用法:
    python bin/apply_human_reviews.py --returned /tmp/ket_qua_nguoi_*.json
"""
import argparse
import glob
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "distill_football"
OUTDIR = ROOT / "references" / "examples_football"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--returned", nargs="+", required=True)
    args = ap.parse_args(argv)

    files = []
    for pat in args.returned:
        files.extend(glob.glob(pat))
    files = sorted(set(files))
    print(f"读入导师文件 {len(files)} 份")

    # 汇总每个候选的确认结果
    verdict = defaultdict(list)   # id -> [(person, answer, note)]
    for f in files:
        d = json.loads(Path(f).read_text(encoding="utf-8"))
        p = d.get("person")
        for c in d.get("cands", []):
            verdict[c["id"]].append((p, c.get("answer", ""), c.get("note", "")))

    ok_ids, no_ids = set(), set()
    for rid, vs in verdict.items():
        answers = [a for _, a, _ in vs if a]
        if answers and all(a == "ok" for a in answers):
            ok_ids.add(rid)
        elif answers:
            no_ids.add(rid)

    print(f"导师判「可用」: {len(ok_ids)} 条 | 判「不可用」: {len(no_ids)} 条")

    # 读候选池(含正文);若不存在则从全文重建
    cand_file = DIST / "candidates_full.jsonl"
    if not cand_file.exists():
        print(f"ERROR: 找不到 {cand_file}", file=sys.stderr)
        return 1
    cands = [json.loads(l) for l in cand_file.read_text(
        encoding="utf-8").splitlines() if l.strip()]
    print(f"候选池 {len(cands)} 条")

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    reviewed, rejected = [], []
    for c in cands:
        rid = c["id"]
        if rid in ok_ids:
            c["type_reviewed"] = True
            c["reviewed_by"] = "human"
            c["reviewed_at"] = stamp
            notes = [n for _, _, n in verdict.get(rid, []) if n]
            if notes:
                c["review_note"] = "; ".join(notes)
            reviewed.append(c)
        elif rid in no_ids:
            c["type_reviewed"] = False
            c["rejected_by_human"] = True
            notes = [n for _, _, n in verdict.get(rid, []) if n]
            if notes:
                c["reject_note"] = "; ".join(notes)
            rejected.append(c)
        else:
            c.setdefault("type_reviewed", False)
            c.setdefault("reviewed_by", None)

    OUTDIR.mkdir(parents=True, exist_ok=True)

    # 按类别输出已确认范文
    by_cat = defaultdict(list)
    for c in reviewed:
        by_cat[c.get("candidate_type", "unknown")].append(c)
    for cat, recs in by_cat.items():
        f = OUTDIR / f"{cat}.jsonl"
        with f.open("w", encoding="utf-8") as fh:
            for r in recs:
                fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  → {f.name}: {len(recs)} 条")

    # 写回候选池(保留全量状态,便于后续追查)
    with cand_file.open("w", encoding="utf-8") as fh:
        for c in cands:
            fh.write(json.dumps(c, ensure_ascii=False) + "\n")

    summary = {
        "reviewed_total": len(reviewed),
        "reviewed_by_cat": {k: len(v) for k, v in by_cat.items()},
        "rejected_total": len(rejected),
        "rejected_ids": [c["id"] for c in rejected],
        "sources": [Path(f).name for f in files],
        "applied_at": stamp,
    }
    (OUTDIR / "_review_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"\n已确认范文 {len(reviewed)} 条 → {OUTDIR}/")
    for cat, recs in by_cat.items():
        print(f"  {cat}: {len(recs)}")
    if rejected:
        print(f"被拒 {len(rejected)} 条(不写入范文池)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
