#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_human_eval.py — 生成给真人评测的扩充盲评包。

设计方案(发挥 10 名员工的统计价值):
  9 场比赛 × 3 组 = 27 篇基础稿;每场重复 2 次(不同随机种子)= 54 篇
  三组:
    A 组:0 条范文(基线)
    B 组:注入 1-2 条**人工确认过的**范文(若确认了的话)
    C 组:注入事实块(事实预处理)
  这样能回答:范文注入 vs 事实预处理 vs 裸基线,哪个更好。

  若尚无人工确认范文,则退化为 2 组(A 裸 / C 事实块)。

输出(全部在 human_eval/ 下,不进仓库):
  blind_pack_<N>.md   —— 每个评审员一份独立乱序的包(10 人各不同)
  score_<N>.csv       —— 对应的打分表
  _KEY.json           —— 编号→来源对照(不发给评审员)
"""
import argparse
import json
import os
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
sys.path.insert(0, str(ROOT / "src"))
OUT = ROOT / "human_eval"


def load_cases():
    """9 个用例(G1-G9)的任务与事实。"""
    reg = ROOT / "eval" / "regression"
    cases = []
    # 真实比赛
    rm = reg / "real_matches_20261013"
    if rm.exists():
        emap = json.loads((rm / "_eval_map.json").read_text(encoding="utf-8"))
        for gid, (task, fname) in emap.items():
            fj = rm / (fname + ".json")
            facts = json.loads(fj.read_text(encoding="utf-8")) if fj.exists() else None
            cases.append({"gid": gid, "task": task, "facts": facts})
    return cases


def gen(case, arm, seed, client, vw):
    """生成一篇稿子。arm: 'bare' | 'facts' | 'examples'。"""
    facts = case["facts"] if arm == "facts" else None
    use_ex = (arm == "examples")
    try:
        r = vw.write(client, case["task"], genre="football_ket_qua",
                     profile="full", model_tier="large",
                     facts=facts, use_examples=use_ex, gen_kw={
                         "temperature": 0.7, "max_tokens": 1500})
        return r.get("text", "") if isinstance(r, dict) else str(r)
    except Exception as e:
        return f"[ERROR] {e}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--reviewers", type=int, default=10)
    ap.add_argument("--repeats", type=int, default=2)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)

    import llm_client
    import viet_writer as vw
    client = llm_client.LLMClient(None)

    cases = load_cases()
    print(f"用例 {len(cases)} 个, 评审员 {args.reviewers} 人, 每场重复 {args.repeats}")

    arms = ["bare", "facts"]
    if args.dry_run:
        print("(dry-run,不调用模型)")
        return 0

    # 生成全部稿件
    texts = []
    for c in cases:
        for arm in arms:
            for rep in range(args.repeats):
                t = gen(c, arm, rep, client, vw)
                texts.append({"gid": c["gid"], "arm": arm, "rep": rep, "text": t})
                print(f"  {c['gid']} {arm} rep{rep}: {len(t)} 字符", flush=True)

    n = len(texts)
    for rv in range(1, args.reviewers + 1):
        rnd = random.Random(1000 + rv)
        idx = list(range(n))
        rnd.shuffle(idx)
        # 每人只评一个子集(每场 2 篇),减轻工作量
        pick = idx[: min(40, n)]
        bd = []
        rows = []
        for i, j in enumerate(pick, 1):
            code = f"R{rv:02d}-{i:02d}"
            t = texts[j]
            bd.append(f"## {code}\n\n{t['text']}\n")
            rows.append((code, t["gid"], t["arm"]))
        (OUT / f"blind_pack_{rv:02d}.md").write_text(
            "# Phiếu chấm mù — bản tin kết quả bóng đá\n\n"
            "Đọc từng bài và cho điểm theo 4 tiêu chí bên dưới. "
            "KHÔNG cố đoán bài do công cụ nào viết.\n\n"
            "**Tiêu chí**: 1) Đúng sự thật (0-2) 2) Tự nhiên (1-5) "
            "3) Đúng chuẩn báo chí (1-5) 4) Có thể đăng (có/sửa nhỏ/không)\n"
            "**Quan trọng nhất**: cột 'Câu cần sửa' — chép nguyên câu sai và "
            "viết lại cho đúng.\n\n---\n\n" + "\n---\n\n".join(bd),
            encoding="utf-8")
        import csv
        with (OUT / f"score_{rv:02d}.csv").open("w", newline="",
                                                 encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(["ma_bai", "dung_su_that(0-2)", "tu_nhien(1-5)",
                        "dung_chuan_bao_chi(1-5)",
                        "dang_xuat_ban(co/sua_nho/khong)", "cau_can_sua", "ghi_chu"])
            for code, _, _ in rows:
                w.writerow([code, "", "", "", "", "", ""])
    (OUT / "_KEY.json").write_text(json.dumps(
        {"note": "不发给评审员", "meta": [
            {"gid": c["gid"], "arm_keys": arms} for c in cases]},
        ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已生成 {args.reviewers} 份包 → {OUT}/blind_pack_XX.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
