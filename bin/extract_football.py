#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_football.py — 第三阶段:足球素材全量抽取(支持断点续跑)。

用法:
    python bin/extract_football.py --out distill_football --workers 8
    python bin/extract_football.py --out distill_football --status   # 只看进度
    python bin/extract_football.py --out distill_football --merge    # 合并+去重+产出

设计:
    - 每个分片独立处理,结果写 distill_football/parts/<name>.json
      → 已存在的分片直接跳过(容器重启/进程被杀后可续跑)
    - --merge 阶段做全局 MinHash 去重并产出最终文件
    - 产物只含 ID/哈希/年份/长度/标志,不含原文(版权)

赛果收紧口径: 比分(\d{1,2}-\d{1,2}) 且 (进球分钟 或 比分动词)
去重: MinHash 阈值 0.8(merge 阶段全局去重)
泄漏剔除: 5 场真实比赛 + G1-G4 对阵
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path("/lzcapp/document/Knowledge-vietnem/OpenDataLab___WanJuan-Vietnamese/raw")
CATS = ["ket_qua", "truoc_tran", "chuyen_nhuong", "nhan_vat", "social", "betting"]

FOOTBALL_KW = re.compile(
    r"bóng đá|tỷ số|ghi bàn|thủ môn|HLV|V\.?League|Ngoại hạng Anh|"
    r"Champions League|đội tuyển|vòng \d+|phút \d+", re.I)
SCORE_RE = re.compile(r"\b\d{1,2}\s*-\s*\d{1,2}\b")
MIN_RE = re.compile(r"(phút\s*\d+|\b\d{1,3}')", re.I)
GOAL_VERB = re.compile(
    r"mở tỷ số|gỡ hòa|nâng tỷ số|rút ngắn cách biệt|vượt lên dẫn|ấn định", re.I)
PRE_RE = re.compile(r"nhận định|trước trận|đội hình dự kiến|lực lượng|đối đầu", re.I)
TRANSFER_RE = re.compile(r"chuyển nhượng|chiêu mộ|ký hợp đồng|gia nhập", re.I)
PROFILE_RE = re.compile(r"chân dung|sự nghiệp|tiểu sử", re.I)
BET_RE = re.compile(r"soi kèo|tỷ lệ kèo|tài xỉu|kèo châu Á|nhà cái", re.I)
TOURNAMENT_RE = re.compile(
    r"\b(?:World Cup|Euro|Asian Cup|AFF Cup|AFF Suzuki Cup|SEA Games|Olympic|"
    r"U-?\d{2}|Copa America|Confederation|Nations League|Vòng loại)"
    r"[\s\w]*?(19[89]\d|20[0-2]\d)\b", re.I)
FULL_DATE_RE = re.compile(r"\bngày\s+\d{1,2}[/.-]\d{1,2}[/.-](19[89]\d|20[0-2]\d)\b", re.I)
SEASON_RE = re.compile(r"\b(19[89]\d|20[0-2]\d)\s*/\s*\d{2}\b")
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
EN_WORD = re.compile(r"\b(the|and|of|with|for|from|this|that)\b", re.I)

LEAK_EXACT = [
    (re.compile(r"Hải Phòng.{0,80}?1\s*-\s*2.{0,80}?Thanh Hóa", re.I | re.S), "M1"),
    (re.compile(r"Thanh Hóa.{0,80}?2\s*-\s*1.{0,80}?Hải Phòng", re.I | re.S), "M1"),
    (re.compile(r"Hà Nội(?!.*Đà Nẵng).{0,80}?1\s*-\s*0.{0,80}?Bắc Ninh", re.I | re.S), "M2"),
    (re.compile(r"SHB Đà Nẵng.{0,120}?4\s*-\s*3|luân lưu.{0,60}?4\s*-\s*3", re.I | re.S), "M3"),
    (re.compile(r"Đồng Nai.{0,80}?4\s*-\s*3.{0,80}?Bình Minh", re.I | re.S), "M4"),
    (re.compile(r"Braga.{0,80}?1\s*-\s*3.{0,80}?Sporting", re.I | re.S), "M5"),
    (re.compile(r"Sporting.{0,80}?3\s*-\s*1.{0,80}?Braga", re.I | re.S), "M5"),
    (re.compile(r"Thể Công.{0,80}?1\s*-\s*3.{0,80}?Hà Tĩnh", re.I | re.S), "G1"),
    (re.compile(r"Hà Tĩnh.{0,80}?3\s*-\s*1.{0,80}?Thể Công", re.I | re.S), "G1"),
]


def norm(t):
    return unicodedata.normalize("NFC", t or "")


def is_football(t):
    return len(FOOTBALL_KW.findall(t)) >= 2


def is_ket_qua(t):
    return bool(SCORE_RE.search(t)) and bool(MIN_RE.search(t) or GOAL_VERB.search(t))


def classify(t):
    tags = []
    if is_ket_qua(t):
        tags.append("ket_qua")
    if PRE_RE.search(t):
        tags.append("truoc_tran")
    if TRANSFER_RE.search(t):
        tags.append("chuyen_nhuong")
    if PROFILE_RE.search(t):
        tags.append("nhan_vat")
    if len(t) < 600 and re.search(r"[!?]", t):
        tags.append("social")
    if BET_RE.search(t):
        tags.append("betting")
    return tags


def extract_year(t):
    cleaned = TOURNAMENT_RE.sub(" ", t)
    fd = [int(y) for y in FULL_DATE_RE.findall(cleaned) if 1990 <= int(y) <= 2026]
    if fd:
        return max(fd)
    se = [int(m.group(1)) for m in SEASON_RE.finditer(cleaned)
          if 1990 <= int(m.group(1)) <= 2026]
    if se:
        return max(se)
    ys = [int(y) for y in re.findall(r"\b(19[89]\d|20[0-2]\d)\b", cleaned)
          if 1990 <= int(y) <= 2026]
    return max(ys) if ys else None


def is_leak(t):
    for rx, tag in LEAK_EXACT:
        if rx.search(t):
            return tag
    return None


def minhash_sig(toks, n=64):
    h = set()
    for i in range(len(toks) - 2):
        g = toks[i] + " " + toks[i + 1] + " " + toks[i + 2]
        h.add(int(hashlib.md5(g.encode("utf-8", "ignore")).hexdigest()[:8], 16))
    if not h:
        return ()
    return tuple(sorted(h)[:n])


def jaccard_sig(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def process_file(fp):
    """处理单个分片 → 返回 dict(cat -> [rec], counters)。"""
    out = {c: [] for c in CATS}
    c = Counter()
    try:
        with open(fp, encoding="utf-8", errors="ignore") as f:
            for line in f:
                c["lines"] += 1
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                raw = norm((d.get("title") or "") + " " + (d.get("content") or ""))
                if not is_football(raw):
                    continue
                c["football"] += 1
                leak = is_leak(raw)
                if leak:
                    c["leak_" + leak] += 1
                    continue
                tags = classify(raw)
                if not tags:
                    continue
                hid = d.get("id") or hashlib.md5(
                    raw.encode("utf-8", "ignore")).hexdigest()[:16]
                toks = re.findall(r"\w+", raw.lower())
                rec = {
                    "id": hid,
                    "content_hash": hashlib.sha256(
                        raw.encode("utf-8", "ignore")).hexdigest()[:16],
                    "year": extract_year(raw),
                    "len": len(raw),
                    "mt_or_copy": bool(HAN_RE.search(raw)) or len(EN_WORD.findall(raw)) >= 3,
                    "sig": minhash_sig(toks),
                    # 头部片段仅用于人工确认表(截断 300 字符),不进仓库
                    "head": raw[:300],
                }
                for tg in tags:
                    out[tg].append(rec)
                    c["cls_" + tg] += 1
    except Exception as e:
        c["errors"] += 1
        print(f"  [warn] {fp.name}: {e}", file=sys.stderr)
    return out, c


def _worker(args):
    fp, parts_dir = args
    name = fp.name
    dest = Path(parts_dir) / (name + ".json")
    if dest.exists():
        try:
            d = json.loads(dest.read_text(encoding="utf-8"))
            return name, d, True
        except Exception:
            pass  # 损坏则重跑
    out, c = process_file(fp)
    payload = {"counters": dict(c), "cats": {k: v for k, v in out.items()}}
    dest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return name, payload, False


def cmd_run(args):
    outdir = ROOT / args.out
    parts = outdir / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW.rglob("*.jsonl"))
    if args.limit_files:
        files = files[:args.limit_files]
    todo = [f for f in files if not (parts / (f.name + ".json")).exists()]
    print(f"分片 {len(files)} 个,待处理 {len(todo)} 个,{args.workers} 进程", flush=True)
    total = Counter()
    with Pool(args.workers) as pool:
        for i, (name, payload, cached) in enumerate(
                pool.imap_unordered(_worker, [(f, str(parts)) for f in todo]), 1):
            total.update(payload["counters"])
            flag = "(续用)" if cached else ""
            print(f"  [{i}/{len(todo)}] {name} +{payload['counters'].get('football',0)} "
                  f"足球稿{flag}", flush=True)
    # 汇总已有 parts
    allc = Counter()
    for p in parts.glob("*.json"):
        try:
            allc.update(json.loads(p.read_text(encoding="utf-8"))["counters"])
        except Exception:
            pass
    print(f"\n已完成 {len(list(parts.glob('*.json')))}/{len(files)} 分片")
    print(f"扫描行 {allc['lines']:,},足球稿 {allc['football']:,}")
    for k in sorted(allc):
        if k.startswith(("cls_", "leak_")) or k == "errors":
            print(f"  {k}: {allc[k]:,}")
    return 0


def cmd_status(args):
    outdir = ROOT / args.out
    parts = outdir / "parts"
    files = sorted(RAW.rglob("*.jsonl"))
    done = list(parts.glob("*.json")) if parts.exists() else []
    allc = Counter()
    for p in done:
        try:
            allc.update(json.loads(p.read_text(encoding="utf-8"))["counters"])
        except Exception:
            pass
    print(f"进度: {len(done)}/{len(files)} 分片")
    print(f"扫描行 {allc['lines']:,},足球稿 {allc['football']:,}")
    for k in sorted(allc):
        print(f"  {k}: {allc[k]:,}")
    return 0


def cmd_merge(args):
    outdir = ROOT / args.out
    parts = outdir / "parts"
    agg = {c: [] for c in CATS}
    for p in sorted(parts.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for c in CATS:
            agg[c].extend(d["cats"].get(c, []))
    print("原始:", {c: len(v) for c, v in agg.items()})

    # 全局 MinHash 去重(用 LSH 分桶加速:按签名前 4 位分桶)
    print(f"全局去重(阈值 {args.minhash_threshold})...")
    stats, dedup = {}, {}
    for cat in CATS:
        recs = agg[cat]
        kept, buckets = [], {}
        for r in recs:
            sig = r.get("sig") or ()
            if not sig:
                kept.append(r)
                continue
            key = tuple(sig[:4])
            dup = False
            for s in buckets.get(key, []):
                if jaccard_sig(sig, s) >= args.minhash_threshold:
                    dup = True
                    break
            if not dup:
                buckets.setdefault(key, []).append(sig)
                kept.append(r)
        dedup[cat] = kept
        stats[cat] = {
            "raw": len(recs), "dedup": len(kept),
            "recent_raw": sum(1 for r in recs if (r.get("year") or 0) >= 2023),
            "recent_dedup": sum(1 for r in kept if (r.get("year") or 0) >= 2023),
        }
        print(f"  {cat}: {len(recs)} → {len(kept)} (2023+: {stats[cat]['recent_dedup']})")

    # 写盘:去重后的记录(不含 sig;head 单独写给人工确认表)
    for cat, recs in dedup.items():
        with (outdir / f"{cat}.jsonl").open("w", encoding="utf-8") as f:
            for r in recs:
                rr = {k: v for k, v in r.items() if k not in ("sig", "head")}
                f.write(json.dumps(rr, ensure_ascii=False) + "\n")

    # 汇总统计
    files = sorted(RAW.rglob("*.jsonl"))
    allc = Counter()
    for p in parts.glob("*.json"):
        try:
            allc.update(json.loads(p.read_text(encoding="utf-8"))["counters"])
        except Exception:
            pass
    summary = {
        "files_total": len(files),
        "files_done": len(list(parts.glob("*.json"))),
        "lines": allc["lines"], "football": allc["football"],
        "cls_raw": {k[4:]: v for k, v in allc.items() if k.startswith("cls_")},
        "leak": {k[5:]: v for k, v in allc.items() if k.startswith("leak_")},
        "dedup": stats,
        "mt_or_copy": {c: sum(1 for r in v if r["mt_or_copy"])
                       for c, v in dedup.items()},
        "year_hist": {},
    }
    yh = Counter()
    for cat, recs in dedup.items():
        for r in recs:
            y = r.get("year")
            if y:
                yh[y] += 1
    summary["year_hist"] = dict(sorted(yh.items()))
    (outdir / "STATS.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {outdir}/STATS.json")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="distill_football")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit-files", type=int, default=0)
    ap.add_argument("--minhash-threshold", type=float, default=0.8)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args(argv)
    if args.status:
        return cmd_status(args)
    if args.merge:
        return cmd_merge(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
