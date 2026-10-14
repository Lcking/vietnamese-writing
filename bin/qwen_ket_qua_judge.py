#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""qwen_ket_qua_judge.py — 用 Qwen 判断"这篇主体是不是一场比赛的赛果报道"。

这是**简单的二分类题**(是/否),不是质量打分,本地 Qwen 能胜任。
规则粗筛只负责缩小范围;本脚本对粗筛后的**赛果候选**逐条判定。

输出: distill_football/ket_qua_judged.jsonl
      每条加字段: is_match_report (True/False/None-失败), judge_raw, judge_reason

用法:
    python bin/qwen_ket_qua_judge.py --limit 50          # 小样本
    python bin/qwen_ket_qua_judge.py                     # 全部候选
    python bin/qwen_ket_qua_judge.py --workers 4
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

SYS = ("Bạn là trợ lý phân loại tin tức thể thao. Trả lời ngắn gọn, chỉ một từ."    )

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


def call_llm(prompt):
    body = json.dumps({
        "model": MODEL,
        "messages": [{"role": "system", "content": SYS},
                     {"role": "user", "content": prompt}],
        "temperature": 0,
        "max_tokens": 16,
        "chat_template_kwargs": {"enable_thinking": False},
    }).encode("utf-8")
    req = urllib.request.Request(
        BASE + "/chat/completions", data=body,
        headers={"Content-Type": "application/json",
                 "Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        d = json.loads(r.read().decode("utf-8"))
    return d["choices"][0]["message"]["content"].strip()


# ---- 标题特征(评审建议):辅助判断 ----
TITLE_PLUS = [
    re.compile(r"\b\d{1,2}\s*-\s*\d{1,2}\b"),                    # 球队 比分 球队
    re.compile(r"\bKết quả\b", re.I),                                # Kết quả
    re.compile(r"\b(thắng|hòa|thua|hạ|đánh bại)\b", re.I),          # 结果动词
]
TITLE_MINUS = [
    re.compile(r"^[^:]{2,40}:\s"),                                    # 人名加冒号
    re.compile(r"[“\"']"),                                            # 引语
    re.compile(r"^\s*HLV\b", re.I),                                   # HLV 开头
    re.compile(r"\b(Vì sao|Top|Clip|Tags)\b", re.I),                  # 解释/榜单/视频/标签
    re.compile(r"\b(chuyển nhượng|chiêu mộ|ký hợp đồng)\b", re.I),
    re.compile(r"\b(chấn thương|phản ứng trọng tài|soi kèo)\b", re.I),
]


def title_features(title):
    """返回 (加分, 减分)。"""
    plus = sum(1 for rx in TITLE_PLUS if rx.search(title))
    minus = sum(1 for rx in TITLE_MINUS if rx.search(title))
    return plus, minus


def judge(rec):
    t = rec["text"]
    head = t[:400]
    body = t[:2500]
    title = head.split("\n")[0][:150] if "\n" in head else head[:150]
    try:
        ans = call_llm(PROMPT.format(title=title, body=body))
    except Exception as e:
        return {**rec, "is_match_report": None, "judge_raw": f"[ERR] {e}"}
    up = ans.upper()
    yes = bool(re.search(r"\bCÓ\b|^CÓ", up)) and not up.startswith("KHÔNG")
    tp, tm = title_features(title)
    # 标题有强负面特征(减分≥2)时,即使 LLM 说是也降级为否
    if tm >= 2 and tp == 0:
        yes = False
        ans = ans + " [标题特征否决]"
    return {**rec, "is_match_report": yes, "judge_raw": ans[:60],
            "title_plus": tp, "title_minus": tm}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--out", default="distill_football/ket_qua_judged.jsonl")
    ap.add_argument("--infile", default="distill_football/ket_qua.jsonl")
    args = ap.parse_args(argv)

    inp = ROOT / args.infile
    if not inp.exists():
        print(f"ERROR: 找不到 {inp},先跑 --merge", file=sys.stderr)
        return 1
    recs = [json.loads(l) for l in inp.read_text(encoding="utf-8").splitlines()
            if l.strip()]
    if args.limit:
        recs = recs[:args.limit]
    print(f"判定 {len(recs)} 条,{args.workers} 并发...", flush=True)

    out = []
    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        for i, r in enumerate(ex.map(judge, recs), 1):
            out.append(r)
            if i % 10 == 0 or i == len(recs):
                yes = sum(1 for x in out if x.get("is_match_report") is True)
                print(f"  [{i}/{len(recs)}] CÓ={yes}", flush=True)

    outp = ROOT / args.out
    outp.parent.mkdir(parents=True, exist_ok=True)
    with outp.open("w", encoding="utf-8") as f:
        for r in out:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    yes = sum(1 for r in out if r.get("is_match_report") is True)
    no = sum(1 for r in out if r.get("is_match_report") is False)
    err = sum(1 for r in out if r.get("is_match_report") is None)
    print(f"\nCÓ={yes}  KHÔNG={no}  失败={err} ({yes/(yes+no)*100:.0f}% 保留)"
          if yes + no else "\n全部失败")
    print(f"→ {outp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
