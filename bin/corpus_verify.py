#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corpus_verify.py — 用语料反查越南语表达是否真实、地道。

用途：评审指出规则库里的"错误示例/正例"是模型编造的。本工具不从模型拿答案，
而是回到 253 万条真实越南语足球语料里统计某个说法出现多少次、上下文是什么。
这是判定"某个越南语说法到底对不对"的可靠依据。

用法：
  python3 bin/corpus_verify.py "cơn lốc màu da cam"       # 统计出现次数 + 抽样上下文
  python3 bin/corpus_verify.py "da cam" "da橙"           # 对比两个说法
  python3 bin/corpus_verify.py --contains "Người đặc biệt"   # 精确子串（区分大小写）

参数：
  --corpus PATH    语料 jsonl 路径（默认 /home/abc/.hermes/workspace/viet_football/football_corpus.jsonl）
  --max N          最多扫描多少行（默认全量；大语料可用 --max 200000 快速抽样）
  --ctx N          每个命中打印上下文长度（默认 120 字符）
  --samples N      每个说法最多打印几条上下文样本（默认 3）
"""
import sys, os, json, argparse, unicodedata


def norm(s: str) -> str:
    """NFC 规范化 + 小写，用于大小写不敏感匹配。"""
    return unicodedata.normalize("NFC", s).lower()


def main():
    ap = argparse.ArgumentParser(description="用语料反查越南语表达")
    ap.add_argument("phrases", nargs="+", help="要查的说法，可多个（互相独立统计）")
    ap.add_argument("--corpus", default="/home/abc/.hermes/workspace/viet_football/football_corpus.jsonl")
    ap.add_argument("--max", type=int, default=0, help="最多扫描行数（0=全量）")
    ap.add_argument("--ctx", type=int, default=120)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--case-sensitive", action="store_true")
    args = ap.parse_args()

    if not os.path.exists(args.corpus):
        print(f"[错误] 语料不存在: {args.corpus}", file=sys.stderr)
        return 2

    targets = args.phrases
    if args.case_sensitive:
        keys = targets
    else:
        keys = [norm(p) for p in targets]

    counts = {p: 0 for p in targets}
    samples = {p: [] for p in targets}
    total_lines = 0

    with open(args.corpus, encoding="utf-8") as f:
        for line in f:
            if args.max and total_lines >= args.max:
                break
            total_lines += 1
            try:
                obj = json.loads(line)
            except Exception:
                continue
            text = obj.get("text") or obj.get("content") or ""
            if not text:
                continue
            hay = text if args.case_sensitive else norm(text)
            for p, k in zip(targets, keys):
                if k and k in hay:
                    counts[p] += 1
                    if len(samples[p]) < args.samples:
                        idx = hay.find(k)
                        lo = max(0, idx - args.ctx // 2)
                        hi = min(len(text), idx + len(k) + args.ctx // 2)
                        samples[p].append(text[lo:hi].replace("\n", " "))

    print(f"语料: {args.corpus}")
    print(f"扫描行数: {total_lines:,}" + (f" (--max {args.max:,})" if args.max else " (全量)"))
    print("=" * 72)
    for p in targets:
        print(f"\n【{p}】  命中 {counts[p]:,} 条")
        for s in samples[p]:
            print(f"    …{s}…")
        if counts[p] == 0:
            print("    (未命中 — 该说法在语料中不存在，请警惕是否为编造)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
