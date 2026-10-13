#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""example_ab_test.py — 范文池对照实验(评审第 9 条)。

设计要点(本版修正):
  - 两组**同档位、同配置**,唯一差别是范文:A 组 0 条,B 组 1-2 条
  - model_tier 真正传给 vw.write
  - 结果记录:系统提示字符数 + 每条范文的标题与 article_type
  - 支持每个用例重复 N 次(默认 3),支持 API 端点

⚠ 前提:纯对照需要**人工确认过的同类型范文**。当前库里 ket_qua 有 31 条,
但 type_reviewed 全为 False(启发式标注,评审已确认不可靠)。
本脚本照常可跑,但结论必须注明"范文未确认";正式对照待第三阶段产出确认范文。

用法:
    VIET_LLM_DISABLE_THINKING=1 python bin/example_ab_test.py --out eval/results/ab_examples
    python bin/example_ab_test.py --repeat 5 --tier large
    VIET_LLM_BASE_URL=... VIET_LLM_MODEL=... VIET_LLM_API_KEY=... python bin/example_ab_test.py  # API 端点
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


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/results/ab_examples")
    ap.add_argument("--tier", default="large", choices=["small", "large"])
    ap.add_argument("--use-examples", action="store_true",
                    help="打开 large 档范文位(B 组注入范文)")
    ap.add_argument("--allow-unreviewed", action="store_true",
                    help="放宽'必须人工确认'筛选(结果无效,仅调试用)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--repeat", type=int, default=3, help="每用例重复次数(默认 3)")
    ap.add_argument("--max-tokens", type=int, default=1500)
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--pairs", type=int, default=2, help="B 组注入范文条数(1-2)")
    args = ap.parse_args(argv)

    import viet_writer as vw

    cases = load_cases()
    if args.limit:
        cases = cases[:args.limit]

    # 断言(在初始化 LLM 客户端之前):B 组必须真能注入范文,
    # 否则 A/B 两组提示完全相同,实验等于自己和自己比
    if not cases:
        print("ERROR: 没有可用的赛果用例。", file=sys.stderr)
        return 2
    _probe = vw.build_prompt(cases[0][2], profile="full", model_tier=args.tier,
                             use_examples=args.use_examples,
                             allow_unreviewed=args.allow_unreviewed)
    _n_b = _probe["stats"].get("n_examples", 0)
    _metas = _probe.get("examples_meta", [])
    if _n_b == 0:
        print(f"ERROR: B 组注入范文数为 0(tier={args.tier}, "
              f"use_examples={args.use_examples})——A/B 两组将完全相同,实验无效。"
              f"需先有确认过的范文(--use-examples)或显式放宽(--allow-unreviewed)。",
              file=sys.stderr)
        return 2
    if not args.allow_unreviewed:
        _unrev = [m for m in _metas if not m.get("type_reviewed")]
        if _unrev:
            print(f"ERROR: B 组注入的 {len(_unrev)}/{_n_b} 条范文 type_reviewed != True"
                  f"——真正对照实验只允许人工确认过的范文。"
                  f"如确要用未确认范文,请显式加 --allow-unreviewed(结果无效)。",
                  file=sys.stderr)
            return 2
    _warn = "  ⚠ 范文未经确认,结果无效" if args.allow_unreviewed else ""
    print(f"预检通过: B 组可注入 {_n_b} 条范文(tier={args.tier}){_warn}")

    import llm_client
    from check_style import check as style_check

    client = llm_client.LLMClient(None)
    outdir = ROOT / args.out
    outdir.mkdir(parents=True, exist_ok=True)

    # 两组同档位:都用 full(才有范文预算),唯一差别是 allow_unreviewed 开关
    # 说明:lite 范文预算为 0,A/B 无法在同档位下区分"有/无范文",故用 full。
    TIER = args.tier
    results = []
    for case in cases:
        cid, genre, task = case[0], case[2], case[3]
        facts = case[5] if len(case) > 5 else None


        for rep in range(args.repeat):
            for arm, allow_unrev in (("A_no_examples", False), ("B_with_examples", True)):
                gen_kw = dict(temperature=args.temperature, max_tokens=args.max_tokens)
                text = vw.write(
                    client, task, genre=genre, facts=facts,
                    profile="full",                 # 同档位
                    model_tier=TIER,                # 真正传给 write
                    allow_unreviewed=allow_unrev,
                    gen_kw=gen_kw,
                )
                meta = getattr(vw.write, "last_meta", {}) or {}
                # 取系统提示字符数 + 范文元数据
                p = vw.build_prompt(genre, profile="full", model_tier=TIER,
                                    allow_unreviewed=allow_unrev)
                try:
                    issues = style_check(text, facts, task)
                except Exception:
                    issues = []
                results.append({
                    "case": cid, "arm": arm, "rep": rep, "tier": TIER,
                    "system_chars": len(p["system"]),
                    "examples": p["examples_meta"],
                    "n_examples": p["stats"].get("n_examples", 0),
                    "chars": len(text),
                    "blocking": sum(1 for i in issues if i.get("blocking")),
                    "hint": sum(1 for i in issues if i.get("hint_only")),
                    "rules": sorted({i["rule"] for i in issues}),
                    "text": text,
                })
                print(f"  {cid} rep{rep} {arm}: sys={len(p['system'])} "
                      f"范文{p['stats'].get('n_examples',0)}条 阻断={results[-1]['blocking']}")

    (outdir / "results.json").write_text(
        json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")

    a = [r for r in results if r["arm"] == "A_no_examples"]
    b = [r for r in results if r["arm"] == "B_with_examples"]
    ab = sum(r["blocking"] for r in a)
    bb = sum(r["blocking"] for r in b)
    a_ex = sum(1 for m in a[0]["examples"] if True) if a else 0
    b_ex = len(b[0]["examples"]) if b and b[0]["examples"] else 0
    a_types = sorted({m.get("article_type") for r in a for m in r["examples"]})
    b_types = sorted({m.get("article_type") for r in b for m in r["examples"]})
    lines = ["# 第 9 条 范文池对照实验", ""]
    if args.allow_unreviewed:
        lines += ["> ⚠⚠ **范文未经人工确认,本次结果无效。** "
                  "本报告仅用于调试,不得据以判定范文是否有用。", ""]
    lines += [
             f"- 档位: {TIER}(两组相同)",
             f"- 用例: {len(set(r['case'] for r in a))} 个 × 2 组 × {args.repeat} 次",
             f"- A 组范文: {a_ex} 条 (article_type={a_types})",
             f"- B 组范文: {b_ex} 条 (article_type={b_types})",
             "- ⚠ 范文均**未经人工确认**(type_reviewed=False),结论仅作参考",
             "",
             "| 指标 | A 组(0 条范文) | B 组(注入范文) |",
             "|---|---|---|",
             f"| 系统提示字符 | {a[0]['system_chars'] if a else '-'} | {b[0]['system_chars'] if b else '-'} |",
             f"| 阻断级问题合计 | {ab} | {bb} |",
             f"| 提示级问题合计 | {sum(r['hint'] for r in a)} | {sum(r['hint'] for r in b)} |",
             f"| 平均篇幅(字符) | {sum(r['chars'] for r in a)//max(1,len(a))} "
             f"| {sum(r['chars'] for r in b)//max(1,len(b))} |",
             "",
             "## 判定", ""]
    if ab == bb == 0:
        verdict = "两组均无阻断 → 该指标无区分度;需人工盲审或更细指标"
    elif bb < ab:
        verdict = f"B 组阻断更少({bb} < {ab}) → 方向支持范文有用(需确认范文后复验)"
    elif bb > ab:
        verdict = f"B 组阻断更多({bb} > {ab}) → **范文有负面影响**"
    else:
        verdict = f"两组阻断相同({ab}) → 无差异"
    lines.append(verdict)
    (outdir / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:14]))
    print(f"\n→ {outdir}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
