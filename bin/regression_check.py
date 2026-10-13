#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regression_check.py — E4 检查器回归表。

把真实跑出的稿件原文喂给 check_style,断言"必须报/不能报"的规则。
稿件缺失时跳过该行(不报失败),以便在证据文件未就位时也能跑。

用法:
    python bin/regression_check.py            # 跑全部
    python bin/regression_check.py --list     # 列出用例
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
from check_style import check  # noqa: E402

REAL = ROOT / "eval/regression/placeholder_matches_20261013"

# (名称, 事实文件, 稿件路径(相对), 必须报的规则, 不能报的规则)
TABLE = [
    ("grok M5 事实块组", "M5_braga_sporting",
     "docs/operations/evidence/vietnamese-writing-v145-grok-20261013/out/M5_braga_sporting_og_full.txt",
     [], ["S1"]),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--dir", default=None, help="额外扫描的稿件目录")
    args = ap.parse_args()

    if args.list:
        for name, fx, path, must, mustnot in TABLE:
            print(f"{name}: 必须报={must} 不能报={mustnot}")
        return 0

    total, passed, skipped = 0, 0, 0
    for name, fx, rel, must, mustnot in TABLE:
        fp = ROOT / rel
        if not fp.exists():
            print(f"SKIP {name}: 稿件不存在 ({rel})")
            skipped += 1
            continue
        facts = None
        fxpath = REAL / f"{fx}.json"
        if fxpath.exists():
            facts = json.loads(fxpath.read_text(encoding="utf-8"))
        text = fp.read_text(encoding="utf-8")
        rules = {i["rule"] for i in check(text, facts)}
        ok = all(r in rules for r in must) and all(r not in rules for r in mustnot)
        total += 1
        passed += int(ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}: 命中={sorted(rules)} "
              f"(必须报={must}, 不能报={mustnot})")

    # 扫描整个 evidence 目录(如存在),只统计阻断级
    if args.dir:
        d = Path(args.dir)
        if d.exists():
            print(f"\n扫描 {d}:")
            for fp in sorted(d.rglob("*.txt")):
                txt = fp.read_text(encoding="utf-8", errors="ignore")
                blocking = [i["rule"] for i in check(txt) if i.get("blocking")]
                if blocking:
                    print(f"  {fp.name}: 阻断级 {sorted(set(blocking))}")

    print(f"\n结果: {passed}/{total} 通过, {skipped} 跳过")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
