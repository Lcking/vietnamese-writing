#!/usr/bin/env bash
# 真人评测一键流程:解析回传 → 汇总报告 → 提炼改稿
# 用法: bash bin/run_human_eval_pipeline.sh human_eval/returned/*.json
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -eq 0 ]; then
  echo "用法: bash bin/run_human_eval_pipeline.sh <回传的JSON文件...>"
  echo "例:   bash bin/run_human_eval_pipeline.sh human_eval/returned/*.json"
  exit 1
fi

echo "=== 1/2 解析回传 ==="
python3 bin/parse_task_results.py "$@"

echo
echo "=== 2/2 提炼编辑改稿 ==="
python3 bin/distill_edits.py

echo
echo "=== 完成 ==="
echo "报告:   human_eval/parsed/REPORT.md"
echo "改稿对: human_eval/parsed/edit_pairs.csv"
echo "归纳:   human_eval/parsed/edit_patterns.md"
