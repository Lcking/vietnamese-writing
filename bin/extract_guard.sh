#!/usr/bin/env bash
# distill_football 抽取看护:进程不在且未完成时自动拉起(每 10 分钟检查)
# 用法: nohup bash bin/extract_guard.sh > distill_football/guard.log 2>&1 &
set -u
cd "$(dirname "$0")/.."
OUT=distill_football
TOTAL=$(find /lzcapp/document/Knowledge-vietnem/OpenDataLab___WanJuan-Vietnamese/raw -name '*.jsonl' 2>/dev/null | wc -l)

while true; do
  DONE=$(ls "$OUT"/parts/*.json 2>/dev/null | wc -l)
  RUNNING=$(pgrep -f "python3 bin/extract_football\.py --out $OUT" | wc -l)
  echo "[$(date '+%F %T')] 进度 $DONE/$TOTAL，运行中=$RUNNING"
  if [ "$DONE" -ge "$TOTAL" ]; then
    echo "[$(date '+%F %T')] 全部分片完成，看护退出"
    break
  fi
  if [ "$RUNNING" -eq 0 ]; then
    echo "[$(date '+%F %T')] 未运行，拉起"
    nohup python3 bin/extract_football.py --out "$OUT" --workers 8 >> "$OUT/run.log" 2>&1 &
    sleep 30
  fi
  sleep 600
done
