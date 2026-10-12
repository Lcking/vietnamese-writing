#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ab_distill_eval.py — A/B: 范文池质量对生成质量的影响。

设计:同一模型、同一评测集、同一配置(lite),只换 few-shot 范文来源:
  A 组(对照):现有 examples/football/*.jsonl(启发式精选)
  B 组(实验):蒸馏 top(模型打分选出的精品)

指标:
  1. 自动规则(禁词/必含词/状态断言/因果) — run_eval 判据
  2. 虚构检测器疑点数(状态断言+因果,越少越好)
  3. 长度/耗时
  4. 抽样人工读(我逐条读,非母语,标注局限)

Dùng:
    python bin/ab_distill_eval.py --examples-a examples/football \
        --examples-b /tmp/distill_selected.jsonl \
        --out eval/results/ab_distill
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
sys.path.insert(0, str(ROOT / "src"))

# 与 run_eval.CASES 对齐的精简评测集(11 案例;F 组专测虚构)
CASES = [
    ("A1", "news", "football_tin_tuc",
     "Viết bản tin: U23 Việt Nam thắng U23 Malaysia 2-0 ở vòng loại, Quang Hải ghi bàn phút 67.",
     {"forbid": [], "expect": ["2-0"]}),
    ("A2", "news", "football_tin_tuc",
     "Viết bản tin: CLB Hà Nội bổ nhiệm HLV mới thay HLV cũ. Không nêu tên cụ thể.",
     {"forbid": [], "expect": []}),
    ("B1", "pre_match", "football_pre_match",
     "Nhận định trước trận Việt Nam — Indonesia tối mai. Không khẳng định chắc chắn kết quả.",
     {"forbid": ["chắc chắn thắng", "sẽ thắng đậm"], "expect": []}),
    ("C1", "social", "social_post",
     "Viết bài đăng ngắn: Việt Nam vào chung kết AFF Cup. Không bịa cảnh khán đài.",
     {"forbid": [], "expect": []}),
    ("C2", "social", "social_post",
     "Đăng tin: chưa xác nhận việc HLV từ chức. Phải nêu rõ 'chưa xác nhận'.",
     {"forbid": [], "expect": ["chưa xác nhận", "chưa kiểm chứng", "chưa có thông tin chính thức"]}),
    ("F1", "omit_missing", "social_post",
     "Đăng kết quả: Việt Nam thắng 2-0, Quang Hải ghi bàn phút 67. "
     "(Chỉ có vậy — không có thông tin khán giả, vòng sau.)",
     {"forbid": [], "expect": [], "no_fab": ["trạng thái khẳng định (chưa/đang chờ)",
                                              "quan hệ nhân quả"]}),
    ("F2", "omit_missing", "football_tin_tuc",
     "Viết tin ngắn. Dữ kiện: (1) Cầu thủ rời sân ở phút 58. "
     "(2) CLB thông báo cầu thủ bị đau cổ chân phải. Hai dữ kiện riêng biệt.",
     {"forbid": [], "expect": [], "no_fab": ["quan hệ nhân quả"]}),
    ("F3", "omit_missing", "football_tin_tuc",
     "Viết tin: 'Nếu kịp hoàn tất đăng ký, cầu thủ này có thể đá chính.' "
     "Tiêu đề PHẢI giữ điều kiện 'nếu/có thể'.",
     {"forbid": [], "expect": [], "no_fab": ["trạng thái khẳng định (chưa/đang chờ)"]}),
]


def load_examples(path):
    """path 可以是目录(9 个文件)或单 jsonl(蒸馏结果)。返回 {genre: [block,...]}"""
    from pathlib import Path as P
    p = P(path)
    rows = []
    if p.is_dir():
        for f in sorted(p.glob("*.jsonl")):
            for line in open(f, encoding="utf-8"):
                try:
                    rows.append(json.loads(line))
                except Exception:
                    pass
    else:
        rows = [json.loads(l) for l in open(p, encoding="utf-8")]
    # 按 genre 分桶(蒸馏结果没有 genre 字段,统一按标题关键词粗分)
    by_genre = {}
    for r in rows:
        g = r.get("genre") or r.get("theme")
        if not g:
            # 粗分:标题/正文含特定词 → 归入相近体裁
            t = (r.get("title", "") + " " + r.get("content", "")).lower()
            if any(w in t for w in ["nhận định", "trước trận", "soi kèo"]):
                g = "football_pre_match"
            elif any(w in t for w in ["chuyển nhượng", "chiêu mộ", "ký hợp đồng"]):
                g = "football_chuyen_nhuong"
            else:
                g = "football_tin_tuc"
        by_genre.setdefault(g, []).append(r)
    return by_genre


def build_examples_text(genre, pool, n=4, max_chars=900):
    """从池子里取前 n 条组 few-shot 文本。"""
    if not pool:
        return "", []
    HEADER = ("## Ví dụ mẫu (CHỈ tham khảo cách diễn đạt — KHÔNG phải dữ kiện)\n\n")
    blocks = []
    used = 0
    for r in pool[:n * 3]:
        t = (r.get("title") or "")[:80]
        c = (r.get("content") or "")[:max_chars]
        block = f"[{t}]\n{c}"
        blocks.append(block)
        used += len(block)
        if len(blocks) >= n:
            break
    return HEADER + "\n\n---\n\n".join(blocks), [r.get("content_sha256", "")[:12] for r in pool[:len(blocks)]]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--examples-a", required=True, help="对照范文池(目录或jsonl)")
    ap.add_argument("--examples-b", required=True, help="蒸馏范文池(jsonl)")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--n-examples", type=int, default=4)
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    from llm_client import LLMClient
    client = LLMClient({
        "base_url": os.environ.get("VIET_LLM_BASE_URL", "http://192.168.31.34:8005/v1"),
        "api_key": os.environ.get("VIET_LLM_API_KEY", "dummy"),
        "model": os.environ.get("VIET_LLM_MODEL", "qwen-3.8-27b-awq"),
        "disable_thinking": True,
        "timeout": 150,
    })
    import viet_writer as vw

    poolA = load_examples(args.examples_a)
    poolB = load_examples(args.examples_b)

    from check_fabrication import find_fabrications
    NEG = ["không", "chẳng", "chưa", "đừng", "tránh"]

    def hit_neg(text, w):
        low = text.lower(); wl = w.lower(); pos = 0
        while True:
            i = low.find(wl, pos)
            if i < 0: return False
            if not any(n in low[max(0, i - 50):i] for n in NEG): return True
            pos = i + len(wl)

    def hit_expect(text, w):
        import re
        low = text.lower()
        parts = [re.escape(x) for x in w.lower().split()]
        return re.search(r"\b" + r"\W+(?:\w+\W+){0,2}".join(parts), low) is not None

    results = []
    for group_name, pool in (("A_heuristic", poolA), ("B_distilled", poolB)):
        for cid, gname, genre, prompt, rules in CASES:
            ex_text, ex_ids = build_examples_text(genre, pool.get(genre, []), args.n_examples)
            system = "\n\n---\n\n".join([
                open(ROOT / "prompts" / "system_vi_writer.md", encoding="utf-8").read(),
                open(ROOT / "references" / ("social_post.md" if genre == "social_post"
                      else "football_pre_match.md" if genre == "football_pre_match"
                      else "football_tin_tuc.md"), encoding="utf-8").read(),
                ex_text,
            ])
            user = vw.build_user_prompt(prompt, genre)
            t0 = time.time()
            try:
                res = client.chat(system, user, max_tokens=2000, temperature=0.7)
                text, fr = res.text, res.finish_reason
            except Exception as e:
                text, fr = f"[ERROR] {e}", "error"
            dt = round(time.time() - t0, 1)

            low = text.lower()
            hit_forbid = [w for w in rules["forbid"] if hit_neg(text, w)]
            hit_expect_list = [w for w in rules["expect"] if hit_expect(text, w)]
            fab = find_fabrications(prompt, text)
            fab_v = [f["khớp"] for f in fab if f["nhóm"] in rules.get("no_fab", [])]

            rec = {
                "group": group_name, "id": cid, "genre": genre,
                "chars": len(text), "seconds": dt, "finish_reason": fr,
                "forbidden_hit": hit_forbid, "expected_hit": hit_expect_list,
                "fab_violations": fab_v,
                "examples_used": ex_ids,
                "output": text,
            }
            results.append(rec)
            fn = f"{group_name}_{cid}.json"
            with open(os.path.join(args.out, fn), "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            print(f"  {group_name} {cid}: {len(text)}字 {dt}s fr={fr} "
                  f"fab={len(fab_v)}", flush=True)

    # 汇总
    print("\n" + "=" * 60)
    print("A/B 汇总")
    print("=" * 60)
    for g in ("A_heuristic", "B_distilled"):
        rs = [r for r in results if r["group"] == g]
        ok = sum(1 for r in rs if r["finish_reason"] != "error")
        fab_total = sum(len(r["fab_violations"]) for r in rs)
        f_ok = sum(1 for r in rs if r["id"].startswith("F") and not r["fab_violations"])
        f_tot = sum(1 for r in rs if r["id"].startswith("F"))
        avg_c = sum(r["chars"] for r in rs) / max(1, len(rs))
        print(f"  {g:14s}: {ok}/{len(rs)} 成功, 平均{avg_c:.0f}字, "
              f"虚构疑点{fab_total}, F组通过 {f_ok}/{f_tot}")


if __name__ == "__main__":
    main()
