#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""hydrate_examples.py — 给已确认范文补回完整正文。

问题: candidates_full.jsonl 只存了 head(前 300 字符),
      作为范文注入信号太弱(现有范文池 content 约 1700 字符)。
做法: 从 distill_work/football_full/ 按 id 找到全文,写入 content 字段,
      并转成 examples/football/ 的既有格式(title/content/len/...)。

用法:
    python bin/hydrate_examples.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import extract_football as ef  # noqa: E402

SRC = ROOT / "references" / "examples_football"
OUT = ROOT / "examples" / "football"


def main():
    files = sorted(SRC.glob("*.jsonl"))
    if not files:
        print("ERROR: 没有已确认范文", file=sys.stderr)
        return 1

    # 收集需要补全的 id
    need = {}
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            if r.get("type_reviewed") is True:
                need[r["id"]] = {"cat": f.stem, "rec": r}
    print(f"待补全 {len(need)} 条")

    # 扫全文找正文
    found = {}
    for fp in sorted(ef.FULLDIR.glob("*.jsonl")):
        if len(found) >= len(need):
            break
        with fp.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                rid = d.get("id")
                if rid in need and rid not in found:
                    found[rid] = d
        print(f"  {fp.name}: 累计找到 {len(found)}/{len(need)}", flush=True)

    # 写出:按已有 examples/football 格式
    OUT.mkdir(parents=True, exist_ok=True)
    by_cat = {}
    missing = []
    for rid, info in need.items():
        d = found.get(rid)
        if not d:
            missing.append(rid)
            continue
        text = (d.get("text") or "").strip()
        if not text:
            missing.append(rid)
            continue
        # title = 首行(越南语稿件首行通常是标题)
        lines = [l.strip() for l in text.split("\n") if l.strip()]
        title = lines[0][:200] if lines else ""
        out = {
            "id": rid,
            "theme": "ket_qua" if info["cat"] == "ket_qua" else info["cat"],
            "title": title,
            "content": text,
            "len": len(text),
            "source_url": "",
            "publisher": "",
            "published_at": f"{d.get('year') or ''}-01-01" if d.get("year") else "",
            "collected_at": "2026-10-27",
            "original_id": rid,
            "source_dataset": "WanJuan-Vietnamese",
            "language": "vi",
            "sport": "football",
            "genre": "football_ket_qua" if info["cat"] == "ket_qua" else info["cat"],
            "review_status": "native_confirmed",
            "license_or_attribution": "Shanghai AI Lab (OpenDataLab), CC BY 4.0",
            "article_type": info["cat"],
            "type_reviewed": True,
            "reviewed_by": info["rec"].get("reviewed_by", "human"),
            "reviewed_at": info["rec"].get("reviewed_at", ""),
        }
        by_cat.setdefault(info["cat"], []).append(out)

    for cat, recs in by_cat.items():
        p = OUT / f"{cat}_reviewed.jsonl"
        with p.open("w", encoding="utf-8") as f:
            for r in recs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  → {p.name}: {len(recs)} 条")

    lens = [r["len"] for recs in by_cat.values() for r in recs]
    if lens:
        print(f"\n正文长度: min={min(lens)} max={max(lens)} avg={sum(lens)//len(lens)}")
    if missing:
        print(f"⚠ 未找到全文 {len(missing)} 条: {missing[:5]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
