#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qwen_judge_bulk.py — 对全量赛果候选做 Qwen 二分类(按年份闸门预筛)。

为什么要预筛:
  全量赛果候选 25 万条,逐条 Qwen 要 60+ 小时。
  候选范文只需要 2021+ 的,且最终只要 30 条/类 →
  先用年份闸门(2021+)缩小,再按 ket_qua_score 排序取前 N 送 Qwen。

用法:
    python bin/qwen_judge_bulk.py --year-from 2021 --top 3000     # 只判定高分前 3000
    python bin/qwen_judge_bulk.py --year-from 2021                 # 全部 2021+
"""
import argparse
import json
import os
import re
import sys
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import extract_football as ef  # noqa: E402

BASE = os.environ.get("VIET_LLM_BASE_URL", "http://192.168.31.34:8005/v1")
MODEL = os.environ.get("VIET_LLM_MODEL", "qwen-3.8-27b-awq")
KEY = os.environ.get("VIET_LLM_API_KEY", "dummy")
TIMEOUT = int(os.environ.get("VIET_LLM_TIMEOUT", "300"))

PROMPT = """Câu hỏi: Bài viết dưới đây có phải là BẢN TIN KẾT QUẢ một trận bóng đá không?

Trả lời ĐÚNG MỘT trong hai từ: CÓ hoặc KHÔNG.

Tiêu chí "CÓ": bài viết tường thuật/tóm tắt kết quả một trận bóng đá cụ thể
(có tỷ số, diễn biến bàn thắng, đội thắng/thua rõ ràng).

Tiêu chí "KHÔNG": bài về chuyển nhượng, nhận định trước trận, chân dung cầu thủ,
danh sách/bảng xếp hạng, tin chấn thương, chỉ trích trọng tài, soi kèo cá cược,
môn thể thao khác, hoặc bài chỉ nhắc tới tỷ số như ví dụ minh hoạ.

Tiêu đề: {title}

Nội dung (trích):
{body}

Trả lời:"""


def call(prompt):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0, "max_tokens": 16,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read().decode())["choices"][0]["message"]["content"].strip()


def load_candidates(year_from, top):
    """从全文文件里取赛果稿,按年份闸门 + 排序分截断。"""
    ids = set()
    for l in (ROOT / "distill_football" / "ket_qua_ids.jsonl").read_text(
            encoding="utf-8").splitlines():
        if l.strip():
            ids.add(json.loads(l)["id"])
    out = []
    for fp in sorted(ef.FULLDIR.glob("*.jsonl")):
        with fp.open(encoding="utf-8", errors="ignore") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                if r.get("id") not in ids:
                    continue
                y = r.get("year")
                if year_from and (not y or y < year_from):
                    continue
                t = r.get("text", "")
                if ef.is_aggregator(t) or ef.OTHER_SPORT_TEAMS.search(t):
                    continue
                out.append({"id": r["id"], "year": y, "text": t,
                            "score": ef.ket_qua_score(t)})
    out.sort(key=lambda x: -x["score"])
    return out[:top] if top else out


def judge_one(rec):
    t = rec["text"]
    title = t[:150].split("\n")[0]
    try:
        ans = call(PROMPT.format(title=title, body=t[:2500]))
    except Exception as e:
        return {**rec, "is_match_report": None, "judge_raw": f"[ERR]{e}"}
    up = ans.upper()
    yes = bool(re.search(r"\bCÓ\b|^CÓ", up)) and not up.startswith("KHÔNG")
    # 标题特征否决
    tp = sum(1 for rx in [re.compile(r"\b\d{1,2}\s*-\s*\d{1,2}\b"),
                          re.compile(r"\bKết quả\b", re.I),
                          re.compile(r"\b(thắng|hòa|thua|hạ|đánh bại)\b", re.I)]
             if rx.search(title))
    tm = sum(1 for rx in [re.compile(r"^[^:]{2,40}:\s"),
                          re.compile(r"[“\"']"),
                          re.compile(r"^\s*HLV\b", re.I),
                          re.compile(r"\b(Vì sao|Top|Clip|Tags)\b", re.I)]
             if rx.search(title))
    if tm >= 2 and tp == 0:
        yes = False
    return {**rec, "is_match_report": yes, "judge_raw": ans[:20]}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--year-from", type=int, default=2021)
    ap.add_argument("--top", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="distill_football/ket_qua_full_judged.jsonl")
    args = ap.parse_args(argv)

    cands = load_candidates(args.year_from, args.top)
    print(f"候选(年份>={args.year_from}, top={args.top or '全部'}): {len(cands)}",
          flush=True)
    if not cands:
        return 1
    outp = ROOT / args.out
    with outp.open("w", encoding="utf-8") as f, \
            ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, r in enumerate(ex.map(judge_one, cands), 1):
            f.write(json.dumps({k: v for k, v in r.items() if k != "text"},
                               ensure_ascii=False) + "\n")
            if i % 50 == 0 or i == len(cands):
                print(f"  [{i}/{len(cands)}]", flush=True)
    recs = [json.loads(l) for l in outp.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    yes = sum(1 for r in recs if r.get("is_match_report") is True)
    print(f"\nCÓ={yes} / {len(recs)} ({yes/len(recs)*100:.0f}%)")
    print(f"→ {outp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
