#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
summarize_eval.py — Tổng hợp kết quả eval thành bảng so sánh raw / min / full.

Đọc eval/results/index.json (do run_eval.py sinh ra) và in bảng:
  - số ký tự trung bình theo cấu hình
  - số ca vi phạm bẫy (forbidden_hit) theo cấu hình
  - số ca thiếu thông tin bắt buộc (expected_hit rỗng dù có yêu cầu)
  - thời gian trung bình

Dùng: python bin/summarize_eval.py --results eval/results
"""
import argparse, json, os
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--results", default="eval/results")
    args = ap.parse_args()

    path = os.path.join(args.results, "index.json")
    if not os.path.exists(path):
        print(f"Không tìm thấy {path}. Chạy: python bin/run_eval.py --out {args.results}")
        return
    with open(path, encoding="utf-8") as f:
        rows = json.load(f)

    by_cfg = defaultdict(list)
    for r in rows:
        by_cfg[r["config"]].append(r)

    print("=" * 74)
    print("TỔNG HỢP ĐÁNH GIÁ — raw vs min vs full")
    print("=" * 74)
    hdr = f"{'Cấu hình':<10}{'Số ca':>6}{'Chữ TB':>10}{'Giây TB':>10}{'Vi phạm bẫy':>14}{'Thiếu bắt buộc':>16}"
    print(hdr)
    print("-" * 74)
    for cfg in ("raw", "min", "full"):
        rs = by_cfg.get(cfg)
        if not rs:
            continue
        n = len(rs)
        avg_chars = sum(r["chars"] for r in rs) / n
        avg_sec = sum(r["seconds"] for r in rs) / n
        viol = sum(1 for r in rs if r["forbidden_hit"])
        # "thiếu bắt buộc" chỉ tính cho ca CÓ yêu cầu (expect không rỗng trong CASES)
        missing = sum(1 for r in rs if r.get("_has_expect") and not r.get("expected_hit"))
        print(f"{cfg:<10}{n:>6}{avg_chars:>10.0f}{avg_sec:>10.1f}{viol:>14}{missing:>16}")

    print("-" * 74)
    # chi tiết vi phạm
    print("\nChi tiết vi phạm bẫy:")
    any_v = False
    for r in rows:
        if r["forbidden_hit"]:
            any_v = True
            print(f"  ⚠ {r['id']}/{r['config']}: {', '.join(r['forbidden_hit'])}")
    if not any_v:
        print("  (không có)")

    # dài hơn KHÔNG đồng nghĩa tốt hơn — cảnh báo
    print("\nLưu ý: 'full' viết dài hơn KHÔNG tự động nghĩa là tốt hơn.")
    print("Cần bước chấm mù bởi người bản ngữ (eval/blind_review.md) mới kết luận được.")


if __name__ == "__main__":
    main()
