#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_review_sheet.py — 生成人工确认表(CSV)。

评审要求:
  - 赛果类 50 条: 抽查精确率(赛果判定是否准)
  - 三类候选范文各 30 条: 赛果/赛前/社交,只取 2023+
  - 只给"建议标签 + 理由",**type_reviewed 由用户确认后写入**
  - 用户结论列留空

用法:
    python bin/make_review_sheet.py --kind audit   # 赛果 50 条精确率抽查
    python bin/make_review_sheet.py --kind examples # 三类候选范文
    python bin/make_review_sheet.py --kind all
"""
import argparse
import csv
import json
import random
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "distill_football"


def load(cat):
    f = DIST / f"{cat}.jsonl"
    if not f.exists():
        return []
    return [json.loads(l) for l in f.read_text(encoding="utf-8").splitlines() if l.strip()]


# 非足球/非赛果的强信号(用于给人工的"建议标签"提示)
NON_MATCH_SIGNALS = [
    (r"HCV|HCB|huy chương|Pencak|Silat|karate|bơi lội|điền kinh|bóng rổ|"
     r"bóng chuyền|tennis|golf|đua xe|cờ vua", "非赛果", "像是其他运动项目"),
    (r"chuyển nhượng|ký hợp đồng|gia nhập|chiêu mộ|mức lương", "非赛果", "像是转会新闻"),
    (r"soi kèo|tỷ lệ kèo|tài xỉu|kèo châu Á|nhà cái|cá độ", "非赛果", "像是博彩内容"),
    (r"nhận định|trước trận|đội hình dự kiến", "赛前", "像是赛前分析"),
    (r"chân dung|sự nghiệp|tiểu sử", "非赛果", "像是人物特写"),
    (r"chòm sao|tử vi|horoscope|cung hoàng đạo|giá vàng|chứng khoán",
     "非赛果", "主题不是足球(星座/财经等)"),
]


def suggest_ket_qua(r):
    """给赛果稿的建议标签 + 理由(仅供参考,不写入 type_reviewed)。"""
    head = r.get("head", "")
    reasons = []
    if re_score(head):
        reasons.append("含比分")
    if re.search(r"phút\s*\d+|\b\d{1,3}'", head):
        reasons.append("含分钟")
    if any(v in head for v in ["mở tỷ số", "gỡ hòa", "nâng tỷ số",
                               "vượt lên dẫn", "rút ngắn", "ấn định"]):
        reasons.append("含比分动词")
    for rx, lab, why in NON_MATCH_SIGNALS:
        if re.search(rx, head, re.I):
            return lab, why
    # 有分钟 + 比分动词 才算强信号
    if len(reasons) >= 3:
        return "赛果", "、".join(reasons) + "(信号较强)"
    if len(reasons) == 1:
        return "待定", "只有" + reasons[0] + ",疑似漏检"
    return "赛果", "、".join(reasons) if reasons else "命中口径但无强信号"


def re_score(t):
    import re
    return bool(re.search(r"\b\d{1,2}\s*-\s*\d{1,2}\b", t))


def suggest_example(r, cat):
    head = r.get("head", "")
    if cat == "ket_qua":
        lab, why = suggest_ket_qua(r)
        return lab, why
    if cat == "truoc_tran":
        if "nhận định" in head or "trước trận" in head:
            return "赛前", "含赛前分析标志词"
        return "其他", "缺少典型赛前特征"
    if cat == "social":
        return "社交短帖", "短文本+口语/感叹语气"
    return "其他", ""


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--kind", choices=["audit", "examples", "all"], default="all")
    ap.add_argument("--n-audit", type=int, default=50)
    ap.add_argument("--n-per-cat", type=int, default=30)
    ap.add_argument("--seed", type=int, default=42)
    args = ap.parse_args(argv)

    random.seed(args.seed)
    DIST.mkdir(exist_ok=True)

    if args.kind in ("audit", "all"):
        kq = load("ket_qua")
        sample = random.sample(kq, min(args.n_audit, len(kq))) if kq else []
        with (DIST / "确认表_赛果抽查.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["编号", "ID", "年份", "正文前300字符",
                        "百晓生建议标签", "建议理由", "用户结论(赛果/非赛果)",
                        "用户备注"])
            for i, r in enumerate(sample, 1):
                lab, why = suggest_ket_qua(r)
                w.writerow([f"A{i:02d}", r["id"], r.get("year") or "",
                            (r.get("head") or "")[:300], lab, why, "", ""])
        print(f"赛果抽查表: {len(sample)} 行 → {DIST}/确认表_赛果抽查.csv")

    if args.kind in ("examples", "all"):
        with (DIST / "确认表_候选范文.csv").open("w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["编号", "类别", "ID", "标题", "年份", "正文前300字符",
                        "百晓生建议标签", "建议理由",
                        "用户结论(可用/不可用)", "用户备注"])
            n = 0
            for cat, cz in [("ket_qua", "赛果"), ("truoc_tran", "赛前"),
                            ("social", "社交短帖")]:
                recs = [r for r in load(cat) if (r.get("year") or 0) >= 2023]
                pick = random.sample(recs, min(args.n_per_cat, len(recs))) if recs else []
                for i, r in enumerate(pick, 1):
                    lab, why = suggest_example(r, cat)
                    w.writerow([f"{cz}{i:02d}", cz, r["id"],
                                "", r.get("year") or "",
                                (r.get("head") or "")[:300], lab, why, "", ""])
                    n += 1
            print(f"候选范文表: {n} 行 → {DIST}/确认表_候选范文.csv")
    return 0


if __name__ == "__main__":
    import re
    sys.exit(main())
