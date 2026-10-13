#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""example_ab_test.py — 评审第 9 条:范文池对照实验。

对 G1-G9 赛果用例跑两组,口径一致:
  A 组:0 条范文
  B 组:注入 1-2 条同类型范文(--allow-unreviewed-examples 打开)

两组都经 viet_writer.write 的真实路径(同一份事实块),只差范文。
比较:阻断级/提示级问题数、篇幅。

前提:仓库现有范文 type_reviewed=False(无人确认),故 B 组用的是**未确认**范文,
结果只作参考;接入人工确认范文后需重跑。

用法:
    python bin/example_ab_test.py --out eval/results/ab_examples
    python bin/example_ab_test.py --limit 3
"""
import argparse
import importlib.util as ilu
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
sys.path.insert(0, str(ROOT / "src"))


def load_cases():
    spec = ilu.spec_from_file_location("re_mod", ROOT / "bin/run_eval.py")
    m = ilu.module_from_spec(spec)
    spec.loader.exec_module(m)
    return [c for c in m.CASES if c[1] == "ket_qua"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/results/ab_examples")
    ap.add_argument("--tier", default="large", choices=["small", "large"])
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--max-tokens", type=int, default=1500)
    ap.add_argument("--temperature", type=float, default=0.7)
    args = ap.parse_args()

    import llm_client
    import viet_writer as vw
    from check_style import check as style_check

    client = llm_client.LLMClient(None)
    outdir = ROOT / args.out
    outdir.mkdir(parents=True, exist_ok=True)

    cases = load_cases()
    if args.limit:
        cases = cases[:args.limit]

    results = []
    for case in cases:
        cid, genre, task = case[0], case[2], case[3]
        facts = case[5] if len(case) > 5 else None

        for arm, allow_unrev, prof in (
                ("A_no_examples", False, "lite"),      # A 组:无范文(lite)
                ("B_with_examples", True, "full")):    # B 组:有范文预算(full)+允许未确认
            text = vw.write(
                client, task, genre=genre, facts=facts,
                profile=prof, allow_unreviewed=allow_unrev,
                gen_kw=dict(temperature=args.temperature, max_tokens=args.max_tokens),
            )
            meta = getattr(vw.write, "last_meta", {}) or {}
            n_ex = meta.get("n_examples", 0)
            try:
                issues = style_check(text, facts, task)
            except Exception as e:
                issues = []
                print(f"    [check error] {e}")
            results.append({
                "case": cid, "arm": arm, "tier": args.tier,
                "examples_injected": n_ex, "chars": len(text),
                "blocking": sum(1 for i in issues if i.get("blocking")),
                "hint": sum(1 for i in issues if i.get("hint_only")),
                "rules": sorted({i["rule"] for i in issues}),
                "text": text,
            })
            print(f"  {cid} {arm}: 范文{n_ex}条 阻断={results[-1]['blocking']} "
                  f"篇幅={len(text)} 规则={results[-1]['rules']}")

    (outdir / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    a = [r for r in results if r["arm"] == "A_no_examples"]
    b = [r for r in results if r["arm"] == "B_with_examples"]
    ab = sum(r["blocking"] for r in a)
    bb = sum(r["blocking"] for r in b)
    n_ex_b = max((r["examples_injected"] for r in b), default=0)
    lines = ["# 第 9 条 范文池对照实验", "",
             f"- 档位: {args.tier}",
             f"- 用例: {len(a)} 个赛果用例 × 2 组",
             f"- B 组实际注入范文: {n_ex_b} 条/篇",
             "- ⚠ 范文均**未经人工确认**(仓库 473 条 type_reviewed=False),结果仅作参考",
             "",
             "| 指标 | A 组(0 条范文) | B 组(注入范文) |",
             "|---|---|---|",
             f"| 阻断级问题合计 | {ab} | {bb} |",
             f"| 提示级问题合计 | {sum(r['hint'] for r in a)} | {sum(r['hint'] for r in b)} |",
             f"| 平均篇幅(字符) | {sum(r['chars'] for r in a)//max(1,len(a))} "
             f"| {sum(r['chars'] for r in b)//max(1,len(b))} |",
             "",
             "## 判定", ""]
    if ab == bb == 0:
        verdict = "两组均无阻断 → 本指标无区分度;需人工盲审或换更细指标"
    elif bb < ab:
        verdict = f"B 组阻断更少({bb} < {ab}) → 范文有正向作用(样本小,建议扩大复验)"
    elif bb > ab:
        verdict = f"B 组阻断更多({bb} > {ab}) → **范文有负面影响**,不应默认开启"
    else:
        verdict = f"两组阻断相同({ab}) → 无明显差异"
    lines.append(verdict)
    lines += ["", "## 逐用例", ""]
    for r in a:
        x = next((y for y in b if y["case"] == r["case"]), None)
        lines.append(f"- {r['case']}: A={r['blocking']} / B={x['blocking'] if x else '?'}")
    (outdir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:16]))
    print(f"\n→ {outdir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
