#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""distill_edits.py — 从编辑改稿中提炼可执行知识。

输入: human_eval/parsed/edits.jsonl(每条形如
      {"ma_bai":"B01","nguoi":1,"sua":"Câu chưa ổn: A ... \\n Câu nên viết: B ..."})
输出:
  1. human_eval/parsed/edit_pairs.csv   —— 拆好的 (sai, đúng) 对
  2. human_eval/parsed/edit_patterns.md —— 高频模式归纳(供人工确认后进规则卡)
  3. references/editor_examples/*.jsonl —— 若整篇被改写,可作范文种子

用法:
    python bin/distill_edits.py
"""
import argparse
import csv
import json
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 常见"错→对"标记(越南语 + 中文 + 英文)
BAD_MARKS = re.compile(
    r"^\s*(?:câu\s+(?:chưa\s+ổn|sai|không\s+ổn)|sai|chưa\s+ổn|原句|错句|bad|wrong)"
    r"\s*[:：]\s*", re.I)
GOOD_MARKS = re.compile(
    r"^\s*(?:câu\s+nên\s+viết|câu\s+đúng|nên\s+viết|đúng\s+là|修改|改为|应写|正确|good|better|fix)"
    r"\s*[:：]\s*", re.I)


def split_pair(text):
    """把一段改稿拆成 (sai, đúng)。失败返回 (None, None)。"""
    if not text or not text.strip():
        return None, None
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    bad, good = None, None
    for l in lines:
        if BAD_MARKS.match(l) and bad is None:
            bad = BAD_MARKS.sub("", l).strip()
        elif GOOD_MARKS.match(l) and good is None:
            good = GOOD_MARKS.sub("", l).strip()
    if bad and good:
        return bad, good
    # 退路:含 "→" 或 "->" 的单行
    for l in lines:
        if "→" in l or "->" in l:
            a, b = re.split(r"\s*(?:→|->)\s*", l, maxsplit=1)
            a = BAD_MARKS.sub("", a).strip()
            b = GOOD_MARKS.sub("", b).strip()
            if a and b:
                return a, b
    return None, None


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--edits", default="human_eval/parsed/edits.jsonl")
    ap.add_argument("--out", default="human_eval/parsed")
    args = ap.parse_args(argv)

    src = ROOT / args.edits
    outdir = ROOT / args.out
    outdir.mkdir(parents=True, exist_ok=True)
    if not src.exists():
        print(f"ERROR: 找不到 {src}", file=sys.stderr)
        return 1

    edits = [json.loads(l) for l in src.read_text(encoding="utf-8").splitlines()
             if l.strip()]
    pairs, unsplit = [], []
    for e in edits:
        # 新版:网页已按「原句 / 正确写法」两个框分开,直接用
        if e.get("sai") or e.get("dung"):
            if e.get("sai") and e.get("dung"):
                pairs.append({"ma_bai": e.get("ma_bai"), "nguoi": e.get("nguoi"),
                              "sai": e["sai"], "dung": e["dung"],
                              "do_dai": f"{len(e['sai'])}->{len(e['dung'])}"})
            else:
                unsplit.append(e)   # 只填了一半
            continue
        # 旧版:单字符串,需拆
        bad, good = split_pair(e.get("sua", ""))
        if bad and good:
            pairs.append({"ma_bai": e.get("ma_bai"), "nguoi": e.get("nguoi"),
                          "sai": bad, "dung": good,
                          "do_dai": f"{len(bad)}->{len(good)}"})
        else:
            unsplit.append(e)

    with (outdir / "edit_pairs.csv").open("w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=["ma_bai", "nguoi", "sai", "dung", "do_dai"])
        w.writeheader()
        w.writerows(pairs)

    # 归纳:反复出现的替换(词/短语级)
    word_swaps = Counter()
    for p in pairs:
        # 只做短语级粗略比对:找 sai 里出现、dung 里不再出现的关键词组
        sw = re.findall(r"\b[\wÀ-ỹ]{2,}(?:\s+[\wÀ-ỹ]{2,}){0,2}\b", p["sai"])
        for s in sw:
            if s.lower() not in p["dung"].lower() and len(s) > 5:
                word_swaps[s] += 1

    L = ["# 编辑改稿提炼", "",
         f"- 收到改稿 {len(edits)} 条",
         f"- 成功拆成「错→对」对: **{len(pairs)}** 条",
         f"- 未能拆解(需人工看): {len(unsplit)} 条", ""]

    if pairs:
        L += ["## 改稿样例(前 20 条)", "",
              "| 稿件 | 原句(有问题) | 编辑改后 |", "|---|---|---|"]
        for p in pairs[:20]:
            L.append(f"| {p['ma_bai']} | {p['sai'][:70]} | **{p['dung'][:70]}** |")
        L.append("")

    if word_swaps:
        L += ["## 反复出现的可疑表达(需人工确认后进规则卡)", "",
              "| 表达 | 出现次数 |", "|---|---|"]
        for s, c in word_swaps.most_common(25):
            L.append(f"| `{s}` | {c} |")
        L.append("")
        L += ["> **这些只是候选**——必须由人确认「确实不该这么写」才能进规则卡。",
              "> 未经确认的不得写成硬规则。", ""]

    if unsplit:
        L += ["## 未能自动拆解的条目(需人工阅读)", ""]
        for e in unsplit[:10]:
            L.append(f"- `{e.get('ma_bai')}`: {(e.get('sua') or '')[:110]}")
        L.append("")

    L += ["## 下一步", "",
          "1. 人工确认 `edit_pairs.csv` 里的改法是否成立(这是唯一可信来源)",
          "2. 确认后的高频改法 → 写进 `references/cards/*.md` 规则卡",
          "3. 能自动判定的 → 加进 `bin/check_style.py` 作检查项",
          "4. 编辑改定的整篇稿 → 存 `references/editor_examples/` 作范文",
          "5. **重跑生成 + 再请编辑盲评**,确认真的变好了", ""]

    (outdir / "edit_patterns.md").write_text("\n".join(L), encoding="utf-8")
    print(f"改稿 {len(edits)} 条 → 拆出 {len(pairs)} 对,待人工 {len(unsplit)} 条")
    print(f"→ {outdir}/edit_pairs.csv, edit_patterns.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
