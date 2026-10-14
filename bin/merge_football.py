#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""merge_football.py — 合并/统计(高效版 v2)。

关键改进(修 v1 的坑):
  v1 让每个 worker **返回**巨大的 Counter(百万级键),通过 pickle 回主进程,
  进程间传输极慢 → 卡在 23/49 不动。
  v2 让 worker **自己把计数写成小 JSON 文件**(distill_football/mg_parts/),
  主进程只读这些文件做累加 → 传输量从 GB 降到 MB 级。

用法:
    python bin/merge_football.py --out distill_football --workers 8
    python bin/merge_football.py --out distill_football --merge-only
"""
import argparse
import json
import re
import sys
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import extract_football as ef  # noqa: E402


def ngrams(txt, ns=(2, 3, 4), cap=1500):
    """返回该文本的 n 词组计数。

    截断到前 cap 个词:超长稿(合集/聚合页)会拖慢整条管线
    (实测某分片 9.4 万赛果稿 × 4000 词 → 单分片 7 分钟,CPU 密集)。
    词组表统计的是**高频搭配**,前 1500 词足够代表,精度损失可忽略。
    """
    toks = re.findall(r"\w+", txt.lower())[:cap]
    out = Counter()
    for n in ns:
        for i in range(len(toks) - n + 1):
            out[" ".join(toks[i:i + n])] += 1
    return out


def process_shard(args):
    """处理一个分片 → 写 distill_football/mg_parts/<name>.json(已存在则跳过)。"""
    fp, parts_dir = args
    fp = Path(fp)
    parts_dir = Path(parts_dir)
    dest = parts_dir / (fp.name + ".json")
    if dest.exists():
        return fp.name, True
    ng = Counter()
    ents = Counter()
    ent_years = {}
    kq_ids = []
    n_docs = 0
    seen = set()
    with open(fp, encoding="utf-8", errors="ignore") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                r = json.loads(line)
            except Exception:
                continue
            rid = r.get("id")
            if not rid or rid in seen:
                continue
            seen.add(rid)
            y = r.get("year")
            txt = r.get("text", "")
            tags = r.get("tags", [])
            if "ket_qua" in tags:
                kq_ids.append(rid)
                if not ((y or 0) and y < 2015) and not ef.is_aggregator(txt) \
                        and not ef.OTHER_SPORT_TEAMS.search(txt) \
                        and not ef.EF_OFFTOPIC_RE.search(txt[:600]):
                    ng.update(ngrams(txt))
                    n_docs += 1
            for nm in ef.ENT_RE.findall(txt):
                nm = " ".join(nm.split())
                if len(nm) < 4 or nm.lower() in ef.ENT_STOP:
                    continue
                ents[nm] += 1
                if y:
                    e = ent_years.get(nm)
                    if e is None:
                        ent_years[nm] = [y, y]
                    else:
                        if y < e[0]:
                            e[0] = y
                        if y > e[1]:
                            e[1] = y
    parts_dir.mkdir(parents=True, exist_ok=True)
    # 落盘前**先过滤**:只留可能入表的(ngram count>=5,entity count>=3)
    # 否则单分片 json 达 200MB+,8 个 worker 同时写会撑爆 I/O 与内存
    ng_small = {k: v for k, v in ng.items() if v >= 5}
    ents_small = {k: v for k, v in ents.items() if v >= 3}
    ye_small = {k: v for k, v in ent_years.items() if k in ents_small}
    dest.write_text(json.dumps({
        "ng": ng_small, "ents": ents_small, "ent_years": ye_small,
        "kq_ids": kq_ids, "n_docs": n_docs,
    }, ensure_ascii=False), encoding="utf-8")
    return fp.name, False


def cmd_run(args):
    outdir = ROOT / args.out
    parts = outdir / "mg_parts"
    files = sorted(ef.FULLDIR.glob("*.jsonl"))
    todo = [f for f in files if not (parts / (f.name + ".json")).exists()]
    print(f"全文分片 {len(files)} 个,待处理 {len(todo)}", flush=True)
    with Pool(args.workers) as pool:
        for i, (name, cached) in enumerate(
                pool.imap_unordered(process_shard,
                                    [(str(f), str(parts)) for f in todo]), 1):
            print(f"  [{i}/{len(todo)}] {name} {'(续用)' if cached else ''}", flush=True)
    return cmd_merge(args)


def cmd_merge(args):
    outdir = ROOT / args.out
    parts = outdir / "mg_parts"
    ng_total = Counter()
    ents_total = Counter()
    ent_years = {}
    kq_ids = []
    all_docs = 0
    files = sorted(parts.glob("*.json"))
    print(f"合并 {len(files)} 个分片产物...", flush=True)
    for i, p in enumerate(files, 1):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        ng_total.update(d.get("ng", {}))
        ents_total.update(d.get("ents", {}))
        for k, (a, b) in d.get("ent_years", {}).items():
            e = ent_years.get(k)
            if e is None:
                ent_years[k] = [a, b]
            else:
                if a < e[0]:
                    e[0] = a
                if b > e[1]:
                    e[1] = b
        kq_ids.extend(d.get("kq_ids", []))
        all_docs += d.get("n_docs", 0)
        if i % 10 == 0 or i == len(files):
            print(f"  [{i}/{len(files)}] ngram {len(ng_total):,} 实体 {len(ents_total):,}",
                  flush=True)

    uniq = list(dict.fromkeys(kq_ids))
    ng5 = {k: v for k, v in ng_total.items() if v >= 5}
    with (outdir / "ngram_football_ket_qua.tsv").open("w", encoding="utf-8") as f:
        f.write("ngram\tn\tcount\n")
        for k, v in sorted(ng5.items(), key=lambda x: -x[1]):
            f.write(f"{k}\t{len(k.split())}\t{v}\n")
    with (outdir / "entity_names_football.tsv").open("w", encoding="utf-8") as f:
        f.write("name\tcount\tfirst_year\tlast_year\n")
        for nm, v in sorted(ents_total.items(), key=lambda x: -x[1]):
            fy, ly = ent_years.get(nm, ("", ""))
            f.write(f"{nm}\t{v}\t{fy}\t{ly}\n")
    with (outdir / "ket_qua_ids.jsonl").open("w", encoding="utf-8") as f:
        for rid in uniq:
            f.write(json.dumps({"id": rid}, ensure_ascii=False) + "\n")

    summary = {"ngram_rows": len(ng5), "ngram_docs": all_docs,
               "entity_rows": len(ents_total),
               "ket_qua_raw": len(kq_ids), "ket_qua_dedup": len(uniq)}
    (outdir / "MERGE_STATS.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nngram {len(ng5):,} 行 | entity {len(ents_total):,} 行")
    print(f"赛果稿 {len(kq_ids):,} → 去重 {len(uniq):,}")
    print(f"→ {outdir}/ngram_football_ket_qua.tsv, entity_names_football.tsv")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="distill_football")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--merge-only", action="store_true")
    args = ap.parse_args(argv)
    return cmd_merge(args) if args.merge_only else cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
