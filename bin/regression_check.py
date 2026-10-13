#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""regression_check.py — E4 检查器回归表。

把真实跑出的稿件原文喂给 check_style,断言"必须报/不能报"的规则。

用法:
    python bin/regression_check.py            # 跑全部(仓库内稿件)
    python bin/regression_check.py --list     # 列出用例
    python bin/regression_check.py --dir DIR  # 额外扫一个目录(仅不依赖 facts 的阻断规则)
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
from check_style import check  # noqa: E402

REAL = ROOT / "eval/regression/real_matches_20261013"


def _load_map():
    """读 _eval_map.json: {gid: [task_text, file_stem]}。"""
    try:
        return json.loads((REAL / "_eval_map.json").read_text(encoding="utf-8"))
    except Exception:
        return {}


_MAP = _load_map()
# 文件名 → 任务文本(反查)
_BY_FILE = {v[1]: v[0] for v in _MAP.values() if isinstance(v, (list, tuple)) and len(v) >= 2}


def _load_task(stem):
    """按文件名(或 G 编号前缀)取任务文本。"""
    if stem in _BY_FILE:
        return _BY_FILE[stem]
    gid = stem.split("_")[0]
    entry = _MAP.get(gid)
    return entry[0] if entry else None


def _load_facts(stem):
    """按文件名取对应 facts(仓库内 real_matches;取不到返回 None)。"""
    fp = REAL / f"{stem}.json"
    if fp.exists():
        return json.loads(fp.read_text(encoding="utf-8"))
    # 试按 G 编号映射到真实文件
    gid = stem.split("_")[0]
    entry = _MAP.get(gid)
    if entry and len(entry) >= 2:
        fp2 = REAL / f"{entry[1]}.json"
        if fp2.exists():
            return json.loads(fp2.read_text(encoding="utf-8"))
    return None


# (名称, facts 文件名, 稿件路径(相对仓库), 必须报的规则, 不能报的规则)
# 稿件放在 eval/regression/ 内,确保上游 clone 后也存在。
TABLE = [
    ("盲审 B01 (G5) 比分行泄漏", "M1_hai_phong_thanh_hoa",
     "eval/regression/realrun_smoke/B01_haiphong.txt", ["S21"], []),
    ("盲审 B18 (G6) 比分行泄漏", "M2_ha_noi_bac_ninh",
     "eval/regression/realrun_smoke/B18_hanoi.txt", ["S21"], []),
    ("盲审 B06 (G5) 干净稿", "M1_hai_phong_thanh_hoa",
     "eval/regression/realrun_smoke/B06_clean.txt", [], ["S21", "S10", "S11"]),
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

    total, passed, skipped, failed = 0, 0, 0, 0
    for name, fx, rel, must, mustnot in TABLE:
        fp = ROOT / rel
        if not fp.exists():
            print(f"SKIP {name}: 稿件不存在 ({rel})")
            skipped += 1
            continue
        facts = _load_facts(fx)
        text = fp.read_text(encoding="utf-8")
        task = _load_task(fx)
        rules = {i["rule"] for i in check(text, facts, task)}
        ok = all(r in rules for r in must) and all(r not in rules for r in mustnot)
        total += 1
        passed += int(ok)
        failed += int(not ok)
        print(f"{'PASS' if ok else 'FAIL'} {name}: 命中={sorted(rules)} "
              f"(必须报={must}, 不能报={mustnot})")

    # 扫描目录:按文件名尽量取对应 facts/task;取不到则只跑不依赖 facts 的规则
    if args.dir:
        d = Path(args.dir)
        if d.exists():
            print(f"\n扫描 {d}:")
            for fp in sorted(d.rglob("*.txt")):
                txt = fp.read_text(encoding="utf-8", errors="ignore")
                facts = _load_facts(fp.stem)
                task = _load_task(fp.stem)
                if facts is None:
                    print(f"  {fp.name}: (无对应 facts → 仅检查不依赖 facts 的规则)")
                blocking = [i["rule"] for i in check(txt, facts, task)
                            if i.get("blocking")]
                if blocking:
                    print(f"  {fp.name}: 阻断级 {sorted(set(blocking))}")

    print(f"\n结果: {passed}/{total} 通过, {failed} 失败, {skipped} 跳过")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
