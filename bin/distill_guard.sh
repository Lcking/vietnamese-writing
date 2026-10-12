#!/usr/bin/env bash
# distill_guard.sh — 蒸馏管线看护:主进程退出则自动重启(靠 run_distill_all.sh 的断点续跑特性)
#
# 为什么需要:run_distill_all.sh 支持"产物存在则跳过",但进程本身若被 kill
# (会话回收/容器重启等) 不会自动恢复。本脚本每 5 分钟检查一次,发现管线
# 不在运行且未全部完成,就重新拉起,从断点继续。
#
# 用法:
#   setsid bash bin/distill_guard.sh >/dev/null 2>&1 &
set -u
cd "$(dirname "$0")/.."
ROOT=$(pwd)
WORK="$ROOT/distill_work"
GUARD_LOG="$WORK/guard.log"
ALL_LOG="$WORK/run.log"

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*" >> "$GUARD_LOG"; }

export VIET_LLM_BASE_URL="${VIET_LLM_BASE_URL:-http://192.168.31.34:8005/v1}"
export VIET_LLM_API_KEY="${VIET_LLM_API_KEY:-dummy}"
export VIET_LLM_MODEL="${VIET_LLM_MODEL:-qwen-3.8-27b-awq}"
export VIET_LLM_DISABLE_THINKING=1

TOTAL=20   # 子体裁总数

log "看护启动 (总数=$TOTAL)"

while true; do
  done_n=$(ls "$WORK"/*_top.jsonl 2>/dev/null | wc -l)
  if [ "$done_n" -ge "$TOTAL" ]; then
    log "全部完成 ($done_n/$TOTAL),看护退出"
    break
  fi

  # 精确匹配:排除 pgrep 自身命令行;只认真正在跑的 bash run_distill_all.sh
  if pgrep -f "bash .*/run_distill_all\.sh" >/dev/null 2>&1; then
    log "管线运行中 ($done_n/$TOTAL 完成),继续观察"
  else
    log "管线不在运行 ($done_n/$TOTAL 完成) → 重新拉起,从断点继续"
    POOL=8000 SCORE_LIMIT=1200 TOP=500 MIN_Q=7.0 \
      nohup bash "$ROOT/bin/run_distill_all.sh" >> "$ALL_LOG" 2>&1 &
    log "已拉起 PID=$!"
  fi

  sleep 300
done
