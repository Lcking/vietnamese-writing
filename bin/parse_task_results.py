#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""parse_task_results.py — 解析回收的任务 JSON,汇总成可用结论。

用法:
    python bin/parse_task_results.py human_eval/returned/*.json

输入: 每份 ket_qua_nguoi_XX.json(网页导出的)
输出:
    human_eval/parsed/blind_scores.csv  —— 18 篇盲测评分(含交叉验证)
    human_eval/parsed/audit_result.csv  —— 分类抽查(算精确率)
    human_eval/parsed/cands_result.csv  —— 范文确认(可用率)
    human_eval/parsed/edits.jsonl       —— 编辑改稿(最宝贵,进 editor_edits/)
    human_eval/parsed/REPORT.md         —— 汇总报告
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("files", nargs="+")
    ap.add_argument("--out", default="human_eval/parsed")
    args = ap.parse_args(argv)

    outdir = ROOT / args.out
    outdir.mkdir(parents=True, exist_ok=True)

    # 稿件元数据(从原盲审包取标题)
    blindmeta = {}
    src = ROOT / "eval/blind_review_20261013/phieu_cham_mu.md"
    if src.exists():
        txt = src.read_text(encoding="utf-8").split("# Dữ kiện gốc")[0]
        for m in re.finditer(r"## (B\d+) \(trận (G\d+)\)\s*\n\s*\n(.+)", txt):
            blindmeta[m.group(1)] = {"game": m.group(2),
                                     "title": m.group(3).strip().split("\n")[0]}

    blind, audit, cands, edits = [], [], [], []
    people = []
    for fp in args.files:
        p = Path(fp)
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [跳过] {p.name}: {e}", file=sys.stderr)
            continue
        person = d.get("person", p.stem)
        people.append(person)
        for b in d.get("blind", []):
            code = b.get("code")
            blind.append({"nguoi": person, "ma_bai": code,
                          "title": blindmeta.get(code, {}).get("title", ""),
                          "fact": b.get("fact", ""), "nat": b.get("nat", ""),
                          "std": b.get("std", ""), "pub": b.get("pub", ""),
                          "so_cau_sua": len(b.get("fixes") or []),
                          "fix": b.get("fix", ""), "note": b.get("note", "")})
            # 多句改稿:优先用 fixes 数组,兼容旧版单字符串 fix
            pairs = b.get("fixes") or []
            if pairs:
                for k, pr in enumerate(pairs, 1):
                    edits.append({"ma_bai": code, "nguoi": person,
                                  "thu_tu": k,
                                  "sai": (pr.get("sai") or "").strip(),
                                  "dung": (pr.get("dung") or "").strip(),
                                  "note": b.get("note", "")})
            elif (b.get("fix") or "").strip():
                edits.append({"ma_bai": code, "nguoi": person, "thu_tu": 1,
                              "sai": b["fix"], "dung": "",
                              "note": b.get("note", "")})
        for a in d.get("audit", []):
            audit.append({"nguoi": person, "id": a.get("id"),
                          "tra_loi": a.get("answer", "")})
        for c in d.get("cands", []):
            cands.append({"nguoi": person, "id": c.get("id"),
                          "the_loai": c.get("cat", ""),
                          "ket_luan": c.get("answer", ""),
                          "note": c.get("note", "")})

    def write_csv(name, rows):
        if not rows:
            return
        with (outdir / name).open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
        print(f"  {name}: {len(rows)} 行")

    print(f"回收 {len(people)} 份: {people}")
    write_csv("blind_scores.csv", blind)
    write_csv("audit_result.csv", audit)
    write_csv("cands_result.csv", cands)
    with (outdir / "edits.jsonl").open("w", encoding="utf-8") as f:
        for e in edits:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")

    # ---- 汇总报告 ----
    L = ["# 真人评测汇总", ""]

    # A: 盲测(含交叉验证)
    if blind:
        by_code = defaultdict(list)
        for b in blind:
            by_code[b["ma_bai"]].append(b)
        # 数值评分(先只算有值的)
        def avg(seq):
            v = []
            for x in seq:
                try:
                    v.append(float(x))
                except Exception:
                    pass
            return sum(v) / len(v) if v else 0
        nat = avg([b["nat"] for b in blind])
        std = avg([b["std"] for b in blind])
        L += ["## A. 盲测评分", "",
              f"- 参评篇次: {len(blind)}(覆盖 {len(by_code)} 篇不同稿件)",
              f"- 自然度均值: **{nat:.2f}** / 5" if nat else "",
              f"- 规范度均值: **{std:.2f}** / 5" if std else "",
              f"- 能否发表分布: {dict(Counter(b['pub'] for b in blind))}",
              f"- 事实分分布: {dict(Counter(b['fact'] for b in blind))}", ""]
        L += ["### 交叉验证(同一篇被多人评)", "",
              "| 稿件 | 评者数 | 自然度 | 规范度 |", "|---|---|---|---|"]
        for code, items in sorted(by_code.items()):
            if len(items) > 1:
                n = [i["nat"] for i in items if i["nat"]]
                s = [i["std"] for i in items if i["std"]]
                L.append(f"| {code} | {len(items)} | {n} | {s} |")
        L.append("")
        # 低分稿件
        L += ["### 需要重点关注的稿件(自然度 ≤3)", ""]
        for code, items in sorted(by_code.items()):
            ns = [float(i["nat"]) for i in items if i["nat"]]
            if ns and sum(ns) / len(ns) <= 3:
                L.append(f"- **{code}** ({blindmeta.get(code,{}).get('title','')[:50]}) "
                         f"自然度 {sum(ns)/len(ns):.1f}")
        L.append("")

    # B: 抽查
    if audit:
        tot = sum(1 for a in audit if a["tra_loi"])
        co = sum(1 for a in audit if a["tra_loi"] == "co")
        L += ["## B. 分类抽查", "",
              f"- 已答: {tot}",
              f"- 判为'是赛果': {co}",
              f"- **精确率: {co/tot*100:.0f}%**" if tot else "",
              ""]

    # C: 范文确认
    if cands:
        bycat = defaultdict(lambda: Counter())
        for c in cands:
            if c["ket_luan"]:
                bycat[c["the_loai"]][c["ket_luan"]] += 1
        L += ["## C. 范文确认", "",
              "| 类别 | 可用 | 不可用 | 可用率 |", "|---|---|---|---|"]
        for cat, cc in sorted(bycat.items()):
            tot = cc["ok"] + cc["no"]
            L.append(f"| {cat} | {cc['ok']} | {cc['no']} | "
                     f"{cc['ok']/tot*100:.0f}% |" if tot else f"| {cat} | - | - | - |")
        L.append("")

    # D: 改稿
    if edits:
        L += ["## D. 编辑改稿(最宝贵)", "",
              f"- 收到 {len(edits)} 条改稿 → `edits.jsonl`",
              "- 用途:①提炼规则卡 ②作为最权威范文 ③变成检查项", ""]

    (outdir / "REPORT.md").write_text("\n".join(L), encoding="utf-8")
    print(f"\n→ {outdir}/REPORT.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
