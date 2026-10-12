#!/usr/bin/env bash
# run_distill_all.sh — 一键跑完 20 个子体裁的完整蒸馏管线(可断点续跑)
#
# 阶段:scan(粗筛) → score(Qwen精评) → select(择优)
# 特性:
#   - 每个阶段产物落 distill_work/,已存在则跳过(可中断续跑)
#   - 全程日志 distill_work/run.log
#   - 不依赖交互,可 nohup 后台跑通宵
#
# 用法:
#   bash bin/run_distill_all.sh              # 跑全部
#   bash bin/run_distill_all.sh culture_literature   # 只跑一个子体裁
set -u
cd "$(dirname "$0")/.."          # 到 repo 根
ROOT=$(pwd)
RAW=/lzcapp/document/Knowledge-vietnem/OpenDataLab___WanJuan-Vietnamese/raw
WORK="$ROOT/distill_work"
LOG="$WORK/run.log"
mkdir -p "$WORK"

export VIET_LLM_BASE_URL="${VIET_LLM_BASE_URL:-http://192.168.31.34:8005/v1}"
export VIET_LLM_API_KEY="${VIET_LLM_API_KEY:-dummy}"
export VIET_LLM_MODEL="${VIET_LLM_MODEL:-qwen-3.8-27b-awq}"
export VIET_LLM_DISABLE_THINKING=1

# 子体裁定义: 名字|类|level2子类
SUBS=(
  "culture_literature|culture|literature"
  "culture_customs|culture|customs"
  "culture_art|culture|art"
  "culture_religion|culture|religion"
  "local_social|local_life|social"
  "local_entertainment|local_life|entertainment"
  "local_cuisine|local_life|cuisine"
  "local_travel|local_life|travel"
  "local_work|local_life|work"
  "history_history|history_policy|history"
  "history_geography|history_policy|geography"
  "history_heritage|history_policy|heritage"
  "history_military|history_policy|military"
  "prof_institutions|professional_field|institutions"
  "prof_medicine|professional_field|medicine"
  "prof_finance|professional_field|finance"
  "prof_technology|professional_field|technology"
  "prof_academic|professional_field|academic"
  "prof_law|professional_field|law"
  "prof_education|professional_field|education"
)

# 规模参数(可用环境变量覆盖)
POOL=${POOL:-8000}       # 每子类候选池
SCORE_LIMIT=${SCORE_LIMIT:-1200}  # 精评条数
TOP=${TOP:-500}          # 入库条数
MIN_Q=${MIN_Q:-7.0}      # 质量阈值

log() { echo "[$(date '+%m-%d %H:%M:%S')] $*" | tee -a "$LOG"; }

FILTER="${1:-}"

for entry in "${SUBS[@]}"; do
  IFS='|' read -r name cat sub <<< "$entry"
  if [ -n "$FILTER" ] && [ "$FILTER" != "$name" ]; then continue; fi

  POOL_F="$WORK/${name}_pool.jsonl"
  SCORED_F="$WORK/${name}_scored.jsonl"
  TOP_F="$WORK/${name}_top.jsonl"

  log "===== [$name] ($cat/$sub) ====="

  # 1) scan
  if [ -s "$POOL_F" ]; then
    log "  scan: 已存在,跳过 ($(wc -l < "$POOL_F") 条)"
  else
    log "  scan: 开始 (pool=$POOL)"
    python3 bin/distill_generic.py scan --category "$cat" --sub "$sub" \
      --raw-root "$RAW" --out "$POOL_F" --pool "$POOL" 2>&1 | grep -v lzc-sitecustomize | tee -a "$LOG"
    [ -s "$POOL_F" ] || { log "  scan 无产出,跳过"; continue; }
  fi

  # 2) score
  if [ -s "$SCORED_F" ]; then
    log "  score: 已存在,跳过 ($(wc -l < "$SCORED_F") 条)"
  else
    log "  score: 开始 (limit=$SCORE_LIMIT, 约 $((SCORE_LIMIT*19/600)) 分钟)"
    python3 bin/distill_generic.py score --pool "$POOL_F" --out "$SCORED_F" \
      --limit "$SCORE_LIMIT" --shuffle --batch 5 2>&1 | grep -v lzc-sitecustomize | tail -3 | tee -a "$LOG"
    [ -s "$SCORED_F" ] || { log "  score 无产出,跳过"; continue; }
  fi

  # 3) select
  log "  select: 取 top $TOP (min_q=$MIN_Q)"
  python3 bin/distill_generic.py select --scored "$SCORED_F" --out "$TOP_F" \
    --total "$TOP" --min-q "$MIN_Q" 2>&1 | grep -v lzc-sitecustomize | tee -a "$LOG"

  log "  [$name] 完成 ✓"
done

log "===== 全部完成 ====="
ls -la "$WORK"/*_top.jsonl 2>/dev/null | tee -a "$LOG"
