#!/usr/bin/env python3
"""把 distill_work/*_top.jsonl 转成 examples/generic/{subgenre}.jsonl

背景:20 个子体裁各 500 条蒸馏范文一直躺在本地 distill_work/,
从未进入 skill(examples/generic/ 目录不存在),导致通用体裁
(故事/公文/财经/美食/旅游/医学...)注入 0 条范文。

本脚本只做格式转换 + 字段补齐,不改动内容:
  - 补 id / type_reviewed / article_type / source
  - 蒸馏产物没有 URL,source 如实标 unavailable
  - type_reviewed=False:这些是模型打分选的,未经人工确认(见 REPORT.md)

版权:产物含语料正文,examples/generic/ 已在 .gitignore 中,不入库。
干净 clone 的用户跑本脚本需要有 distill_work/ 原文(见 README)。
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "distill_work")
DST = os.path.join(ROOT, "examples", "generic")

# 蒸馏产物文件名前缀 → 通用体裁名
SUBGENRE_MAP = {
    "culture_literature": "van_hoc",
    "culture_customs": "van_hoa_phong_tuc",
    "culture_art": "nghe_thuat",
    "culture_religion": "ton_giao",
    "local_social": "doi_song",
    "local_entertainment": "giai_tri",
    "local_cuisine": "am_thuc",
    "local_travel": "du_lich",
    "local_work": "cong_viec",
    "history_history": "lich_su",
    "history_geography": "dia_ly",
    "history_heritage": "di_san",
    "history_military": "quan_su",
    "prof_institutions": "the_che",
    "prof_medicine": "y_te",
    "prof_finance": "tai_chinh",
    "prof_technology": "cong_nghe",
    "prof_academic": "hoc_thuat",
    "prof_law": "phap_luat",
    "prof_education": "giao_duc",
}


def main():
    os.makedirs(DST, exist_ok=True)
    total = 0
    for prefix, genre in SUBGENRE_MAP.items():
        src = os.path.join(SRC, f"{prefix}_top.jsonl")
        if not os.path.exists(src):
            print(f"  跳过 {prefix}: 无产物")
            continue
        rows = []
        with open(src, encoding="utf-8") as f:
            for line in f:
                r = json.loads(line)
                content = r.get("content") or ""
                if len(content) < 200:
                    continue
                rows.append({
                    "id": f"distill-{prefix}-{r.get('original_id', len(rows))}",
                    "content": content,
                    "article_type": "generic",
                    "type_reviewed": False,   # 模型打分选的，未经人工确认
                    "source": "unavailable",  # WanJuan 无 URL
                    "subgenre": prefix,
                    "category": r.get("category"),
                    "q_score": r.get("q_score") or r.get("h_score"),
                    "review_status": "model_scored_ranking_only",
                })
        out = os.path.join(DST, f"{genre}.jsonl")
        with open(out, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        total += len(rows)
        print(f"  {prefix:22} → {genre:18} {len(rows):4} 条")
    print(f"\n合计 {total} 条 → {DST}")


if __name__ == "__main__":
    sys.exit(main())
