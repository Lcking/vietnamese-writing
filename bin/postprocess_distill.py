#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""postprocess_distill.py — 对已完成的蒸馏产物做后处理(不中断正在跑的管线)。

只读 distill_work/*_{pool,scored,top}.jsonl,输出统计与标定资产到 distill_report/。

子命令:
  calibrate  -- 第 1 条:抽高/中/低分段样本,生成人工标定表
  subgenre   -- 第 4 条:校验子体裁是否分对
  source     -- 第 2 条:提取正文里的来源线索
  hfilter    -- 第 3 条:硬过滤(声调比例/近似去重/机翻残留/长度)
  leak       -- 第 5 条:剔除评测用例相关报道
  ngram      -- 第 6 条:赛果类词组频率表
  entities   -- 第 6 条:名称表
  report     -- 汇总:各子体裁数量 + 分数分布

用法:
    python bin/postprocess_distill.py report
    python bin/postprocess_distill.py calibrate --sub culture_art
"""
import argparse
import json
import re
import sys
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "distill_work"
OUT = ROOT / "distill_report"


def load_jsonl(fp):
    for line in Path(fp).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                yield json.loads(line)
            except Exception:
                continue


def all_subs():
    """所有已有 top 产物的子体裁名。"""
    return sorted(p.name[:-len("_top.jsonl")] for p in WORK.glob("*_top.jsonl"))


def load_top(sub):
    return list(load_jsonl(WORK / f"{sub}_top.jsonl"))


def load_pool(sub):
    fp = WORK / f"{sub}_pool.jsonl"
    return list(load_jsonl(fp)) if fp.exists() else []


def load_scored(sub):
    fp = WORK / f"{sub}_scored.jsonl"
    return list(load_jsonl(fp)) if fp.exists() else []


# ---------------------------------------------------------------- 通用指标
def tone_ratio(text):
    """带声调字符占比(越南语特有)。"""
    if not text:
        return 0.0
    viet = [c for c in text if c.isalpha()]
    toned = [c for c in viet
             if unicodedata.decomposition(c) and unicodedata.decomposition(c)[0] != "<"]
    return len(toned) / max(1, len(viet))


def han_ratio(text):
    """汉字/日韩字符占比(残留信号)。"""
    if not text:
        return 0.0
    n = sum(1 for c in text if "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u30ff")
    return n / max(1, len(text))


def sentences(text):
    return [s for s in re.split(r"(?<=[.!?…])\s+", text or "") if len(s.strip()) > 2]


# ---------------------------------------------------------------- 1 校准
def cmd_calibrate(args):
    OUT.mkdir(exist_ok=True)
    subs = [args.sub] if args.sub else all_subs()
    summary = []
    for sub in subs:
        rows = load_top(sub)
        if not rows:
            continue
        rows = [r for r in rows if isinstance(r.get("q_score"), (int, float))]
        if not rows:
            continue
        rows.sort(key=lambda r: r["q_score"])
        n = len(rows)
        # 高/中/低三段
        buckets = {
            "high": rows[max(0, n - 10):],
            "mid": rows[max(0, n // 2 - 5):n // 2 + 5],
            "low": rows[:10],
        }
        csv = OUT / f"calibration_{sub}.csv"
        with csv.open("w", encoding="utf-8") as f:
            f.write("seg,idx,q_score,title,content_head\n")
            for seg, items in buckets.items():
                for i, r in enumerate(items):
                    head = (r.get("content") or "")[:120].replace('"', "'").replace("\n", " ")
                    f.write(f'{seg},{i},{r["q_score"]},"{(r.get("title") or "")[:80]}","{head}"\n')
        scores = [r["q_score"] for r in rows]
        scores.sort()
        def pct(p):
            return scores[min(len(scores) - 1, int(len(scores) * p))]
        summary.append({
            "sub": sub, "n": n, "min": scores[0], "p10": pct(0.10),
            "median": pct(0.50), "p90": pct(0.90), "max": scores[-1],
            "at_7": sum(1 for s in scores if 6.8 <= s <= 7.2),
            "csv": csv.name,
        })
    # 结论
    lines = ["# 第 1 条 分数校准", "",
             "各子体裁 top 500 的 q_score 分布(用于判断 7.0 卡线是否合理)。", "",
             "| 子体裁 | N | min | p10 | 中位 | p90 | max | 7.0±0.2 条数 | 标定表 |",
             "|---|---|---|---|---|---|---|---|---|"]
    for s in summary:
        lines.append(f'| {s["sub"]} | {s["n"]} | {s["min"]} | {s["p10"]} | {s["median"]} '
                     f'| {s["p90"]} | {s["max"]} | {s["at_7"]} | {s["csv"]} |')
    lines += ["", "## 说明", "",
              "- 标定表每子体裁含 high/mid/low 各 10 条,供人工判好/中/差。",
              "- 人工判完后,计算与 q_score 的一致性(能否分开好与差)。",
              "- 若分不开:入库标准改为'硬过滤后的分数前 N 条',报告中注明分数只用于排序。"]
    (OUT / "CALIBRATION.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:6]))
    print(f"\n→ 输出到 {OUT}/ (每子体裁一个 CSV + CALIBRATION.md)")
    return 0


# ---------------------------------------------------------------- 4 子体裁校验
KET_QUA_RE = re.compile(r"\d+\s*-\s*\d+")
KET_QUA_MINUTE = re.compile(r"(phút\s*\d+|\d+')", re.I)
KET_QUA_VERB = re.compile(r"mở tỷ số|gỡ hòa|nâng tỷ số|rút ngắn cách biệt|vượt lên dẫn|"
                          r"san bằng|ấn định", re.I)

SUB_RULES = {
    "ket_qua": lambda t: bool(KET_QUA_RE.search(t)) and
                         (bool(KET_QUA_MINUTE.search(t)) or bool(KET_QUA_VERB.search(t))),
    "chuyen_nhuong": lambda t: bool(re.search(
        r"chuyển nhượng|ký hợp đồng|chiêu mộ|gia nhập|rời (CLB|đội)|thương vụ|mua|lý|phí", t, re.I)),
    "nhan_dinh": lambda t: bool(re.search(
        r"nhận định|trước trận|soi kèo|dự đoán|sẽ gặp|phân tích|lực lượng|phong độ", t, re.I)),
    "phong_van": lambda t: bool(re.search(
        r"phát biểu|chia sẻ|cho biết|phỏng vấn|tuyên bố|trả lời", t, re.I)),
}


def cmd_subgenre(args):
    OUT.mkdir(exist_ok=True)
    # 找出名字含 ket_qua / chuyen_nhuong / nhan_dinh / phong_van 的子体裁
    subs = all_subs()
    lines = ["# 第 4 条 子体裁校验", ""]
    report = {}
    for sub in subs:
        kind = None
        for k in SUB_RULES:
            if k in sub:
                kind = k
                break
        if kind is None:
            continue
        rows = load_top(sub)
        bad = [r for r in rows if not SUB_RULES[kind](r.get("content") or "")]
        report[sub] = {"kind": kind, "n": len(rows), "suspect": len(bad)}
        lines.append(f"- **{sub}** ({kind}): {len(rows)} 条,疑似分错 {len(bad)} 条 "
                     f"({len(bad)/max(1,len(rows))*100:.1f}%)")
        # 抽 20 条疑似
        if bad:
            sample_f = OUT / f"subgenre_{sub}_suspect.txt"
            with sample_f.open("w", encoding="utf-8") as f:
                for r in bad[:20]:
                    f.write(f"=== {r.get('title')} ===\n{(r.get('content') or '')[:300]}\n\n")
            lines.append(f"  - 抽样: {sample_f.name}")
    (OUT / "SUBGENRE_CHECK.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


# ---------------------------------------------------------------- 2 来源线索
SOURCE_PATTERNS = [
    re.compile(r"(?:Theo|Nguồn|Nguồn tin)\s*:\s*([A-ZĐ][\w.\-]{2,30})", re.I),
    re.compile(r"\(([A-ZĐ][\w.\-]{2,25})\)\s*$", re.M),
    re.compile(r"\b(VnExpress|Thanh Niên|Tuổi Trẻ|Bongdaplus|Znews|Dân Trí|VietnamNet|"
               r"VOV|VTV|Báo Mới|Người Lao Động|Pháp Luật|Tiền Phong|SGGP|HTV)\b", re.I),
]


def extract_source(text):
    if not text:
        return None
    for pat in SOURCE_PATTERNS:
        m = pat.search(text)
        if m:
            return m.group(1).strip()
    return None


def cmd_source(args):
    OUT.mkdir(exist_ok=True)
    subs = [args.sub] if args.sub else all_subs()
    total = Counter()
    per_sub = {}
    for sub in subs:
        rows = load_top(sub)
        c = Counter()
        for r in rows:
            s = extract_source(r.get("content") or "")
            r["source_hint"] = s
            c[s or "(không rõ)"] += 1
        if rows:
            # 写回 source_hint 到一个新文件(不改原 top)
            out_f = OUT / f"source_{sub}.jsonl"
            with out_f.open("w", encoding="utf-8") as f:
                for r in rows:
                    f.write(json.dumps(r, ensure_ascii=False) + "\n")
            per_sub[sub] = c
            total.update(c)
    lines = ["# 第 2 条 来源线索", "", "## 全库来源统计(前 30)", ""]
    for src, n in total.most_common(30):
        lines.append(f"- {src}: {n}")
    lines += ["", "## 各子体裁有来源比例", ""]
    for sub, c in per_sub.items():
        known = sum(v for k, v in c.items() if k != "(không rõ)")
        tot = sum(c.values())
        lines.append(f"- {sub}: {known}/{tot} ({known/max(1,tot)*100:.0f}%)")
    (OUT / "SOURCE_HINT.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:12]))
    print(f"\n→ {OUT}/SOURCE_HINT.md")
    return 0


# ---------------------------------------------------------------- 3 硬过滤
def near_dup_key(text, k=8):
    """用正文的 k 词 shingle 集合做近似的近似去重键。"""
    toks = re.findall(r"\w+", (text or "").lower())
    if len(toks) < k:
        return frozenset()
    return frozenset(" ".join(toks[i:i + k]) for i in range(len(toks) - k + 1))


def cmd_hfilter(args):
    OUT.mkdir(exist_ok=True)
    subs = [args.sub] if args.sub else all_subs()
    stats = {}
    for sub in subs:
        rows = load_pool(sub) or load_top(sub)
        if not rows:
            continue
        n0 = len(rows)
        kept, seen = [], set()
        drop = Counter()
        for r in rows:
            t = r.get("content") or ""
            if tone_ratio(t) < 0.10:
                drop["tone_low"] += 1
                continue
            if han_ratio(t) > 0.02:
                drop["han_residue"] += 1
                continue
            sl = sentences(t)
            if len(sl) < 3:
                drop["too_short"] += 1
                continue
            if len(t) > 12000:
                drop["too_long"] += 1
                continue
            key = near_dup_key(t)
            if key and key in seen:
                drop["near_dup"] += 1
                continue
            if key:
                seen.add(key)
            kept.append(r)
        stats[sub] = {"n0": n0, "kept": len(kept), "drop": dict(drop)}
    lines = ["# 第 3 条 硬过滤(不调用模型)", "",
             "| 子体裁 | 输入 | 保留 | 声调低 | 汉字残留 | 过短 | 过长 | 近似重复 |",
             "|---|---|---|---|---|---|---|---|"]
    for sub, s in stats.items():
        d = s["drop"]
        lines.append(f'| {sub} | {s["n0"]} | {s["kept"]} | {d.get("tone_low",0)} | '
                     f'{d.get("han_residue",0)} | {d.get("too_short",0)} | '
                     f'{d.get("too_long",0)} | {d.get("near_dup",0)} |')
    lines += ["", "## 阈值说明",
              "- 声调比例 <0.10 判为非越南语/被转码(阈值待抽样确认)",
              "- 汉字/日韩残留 >2% 判为翻译残留",
              "- 句数 <3 / 长度 >12000 判为过短/过长",
              "- 近重复:8 词 shingle 集合完全相同"]
    (OUT / "HARD_FILTER.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines[:8]))
    print(f"\n→ {OUT}/HARD_FILTER.md")
    return 0


# ---------------------------------------------------------------- 5 泄漏剔除
LEAK_MATCHES = [
    ("Hải Phòng", "Thanh Hóa", (1, 2)),
    ("Hà Nội", "Bắc Ninh", (1, 0)),
    ("Hà Nội", "SHB Đà Nẵng", (1, 1)),
    ("TP. Đồng Nai", "Bình Minh Sài Gòn", (4, 3)),
    ("Braga", "Sporting", (1, 3)),
    ("Thể Công", "Hà Tĩnh", (1, 3)),
]


def cmd_leak(args):
    OUT.mkdir(exist_ok=True)
    hits = []
    for sub in all_subs():
        for r in load_top(sub):
            t = (r.get("content") or "") + " " + (r.get("title") or "")
            for a, b, (sa, sb) in LEAK_MATCHES:
                if a.lower() in t.lower() and b.lower() in t.lower():
                    if f"{sa}-{sb}" in t or f"{sb}-{sa}" in t:
                        # 收紧:必须同时是球赛语境(进球动词/比赛分钟),排除同名城市的路人新闻
                        sports_ctx = bool(re.search(
                            r"mở tỷ số|gỡ hòa|nâng tỷ số|vượt lên dẫn|rút ngắn|"
                            r"phút\s*\d+|\d+'|bàn thắng|trận đấu|thẻ (đỏ|vàng)", t, re.I))
                        if not sports_ctx:
                            continue
                        hits.append({"sub": sub, "title": r.get("title"),
                                     "match": f"{a} {sa}-{sb} {b}",
                                     "id": r.get("original_id")})
                        break
    lines = ["# 第 5 条 评测泄漏剔除", "",
             f"命中 **{len(hits)}** 条(涉及 G1-G9 用例的对阵):", ""]
    for h in hits[:50]:
        lines.append(f'- [{h["sub"]}] {h["match"]} — {h["title"]}')
    if not hits:
        lines.append("(未命中)")
    (OUT / "LEAK_EXCLUDE.md").write_text("\n".join(lines), encoding="utf-8")
    (OUT / "leak_exclude.json").write_text(json.dumps(hits, ensure_ascii=False, indent=2),
                                           encoding="utf-8")
    print(f"命中 {len(hits)} 条 → {OUT}/LEAK_EXCLUDE.md")
    return 0


# ---------------------------------------------------------------- 6 统计资产
def cmd_ngram(args):
    OUT.mkdir(exist_ok=True)
    src = args.sub or "ket_qua"
    rows = load_pool(src)
    if not rows:
        # 找含 ket_qua 的子体裁
        cands = [s for s in all_subs() if "ket_qua" in s]
        if not cands:
            rows = []
            for s in all_subs():
                rows += load_pool(s)[:800]
        else:
            for s in cands:
                rows += load_pool(s)
    cnt = Counter()
    for r in rows:
        toks = re.findall(r"[a-zà-ỹ]+", (r.get("content") or "").lower())
        for n in (2, 3, 4):
            for i in range(len(toks) - n + 1):
                cnt[" ".join(toks[i:i + n])] += 1
    with (OUT / "ngram_ket_qua.tsv").open("w", encoding="utf-8") as f:
        f.write("ngram\tn\n")
        for g, n in cnt.most_common(5000):
            f.write(f"{g}\t{n}\n")
    print(f"词组表 → {OUT}/ngram_ket_qua.tsv ({len(cnt)} 个 ngram,取前 5000)")
    return 0


def cmd_entities(args):
    OUT.mkdir(parents=True, exist_ok=True)
    name_years = {}
    for sub in all_subs():
        for r in load_top(sub)[:200]:
            t = (r.get("content") or "") + " " + (r.get("title") or "")
            yr = re.search(r"(20\d{2})", t)
            y = int(yr.group(1)) if yr else None
            for m in re.finditer(r"\b([A-ZĐ][\wÀ-ỹ]+(?:\s+[A-ZĐ][\wÀ-ỹ]+){1,3})\b", t):
                nm = m.group(1)
                if len(nm) < 5:
                    continue
                cur = name_years.get(nm)
                if nm not in name_years:
                    name_years[nm] = y
                elif y is not None and (cur is None or y > cur):
                    name_years[nm] = y
    with (OUT / "entity_names.tsv").open("w", encoding="utf-8") as f:
        f.write("name\tlast_year\n")
        for nm, y in sorted(name_years.items(), key=lambda x: -(x[1] or 0)):
            f.write(f"{nm}\t{y or ''}\n")
    print(f"名称表 → {OUT}/entity_names.tsv ({len(name_years)} 个名称)")
    return 0


# ---------------------------------------------------------------- 汇总
def cmd_report(args):
    OUT.mkdir(exist_ok=True)
    lines = ["# 蒸馏后处理汇总", "", "## 各子体裁数量与分数分布", "",
             "| 子体裁 | top 条数 | q_score 中位 | q_score 范围 | scored 条数 |",
             "|---|---|---|---|---|"]
    total = 0
    for sub in all_subs():
        rows = load_top(sub)
        sc = [r["q_score"] for r in rows if isinstance(r.get("q_score"), (int, float))]
        sc.sort()
        n_scored = len(load_scored(sub))
        med = sc[len(sc) // 2] if sc else "-"
        rng = f"{sc[0]}-{sc[-1]}" if sc else "-"
        lines.append(f"| {sub} | {len(rows)} | {med} | {rng} | {n_scored} |")
        total += len(rows)
    lines += ["", f"**入库合计: {total} 条**"]
    (OUT / "REPORT.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0


def main():
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name, fn in [("calibrate", cmd_calibrate), ("subgenre", cmd_subgenre),
                     ("source", cmd_source), ("hfilter", cmd_hfilter),
                     ("leak", cmd_leak), ("ngram", cmd_ngram),
                     ("entities", cmd_entities), ("report", cmd_report)]:
        p = sub.add_parser(name)
        p.add_argument("--sub", default=None)
        p.set_defaults(func=fn)
    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
