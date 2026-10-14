# 第三阶段进行中 — 状态与后续步骤

启动时间：2026-10-14 11:26　提交：v1.6.13

## 正在跑

```
python bin/extract_football.py --out distill_football --workers 8   # 全量 49 分片
bash bin/extract_guard.sh                                            # 每 10 分钟看护
```

- 产物：`distill_football/parts/<name>.json`（每分片一个，已存在则跳过 → **断点续跑**）
- 全文：`distill_work/football_full/<name>.jsonl`（**不进仓库**）
- 查进度：`python bin/extract_football.py --out distill_football --status`
- 预计：10+ 小时（网盘 IO 瓶颈，实测 100 万行 ≈ 63 秒）

## 已确认的参数

- 赛果口径：比分 + 足球语境(±400 字符窗口,≥2 个专属词) + (进球分钟 或 比分动词)
- 排除：其他运动项目、博彩稿（只打 betting）、聚合页、足球无关稿
- 年份闸门：**候选范文只取 2021+**（单分片实测 2021+ 占 46%）
- 词组表：宽口径，只剔 2015 前 + 聚合页 + 无关稿 + 其他运动
- 名称表：不设年份闸门，记录 first/last year
- 泄漏剔除：5 场真实比赛 + G1-G4

## 跑完后的步骤

1. **merge**（全局 MinHash 去重 + 出两张表）
   ```
   python bin/extract_football.py --out distill_football --merge
   ```

2. **Qwen 二分类判定**（对合并后的赛果候选；已验证精确率 96%）
   ```
   VIET_LLM_BASE_URL=http://192.168.31.34:8005/v1 \
   VIET_LLM_MODEL=qwen-3.8-27b-awq VIET_LLM_API_KEY=dummy \
   python bin/qwen_ket_qua_judge.py --workers 4 \
       --out distill_football/ket_qua_judged.jsonl
   ```

3. **选候选范文**（三类各 30 条，2021+，越南/欧洲各半）
   ```
   python bin/select_candidates.py --n 30
   ```

4. **生成确认表**交用户
   ```
   python bin/make_review_ket_qua.py    # 赛果抽查 50 条
   ```

5. 汇报：修正后年份分布、赛果数量、两表前 200 行、三类候选清单

## 本阶段不做（等人工确认范文）

- 重跑范文对照实验
- 建范文池

## 关键数字（单分片基线，供全量对比）

| 项目 | 值 |
|---|---|
| 扫描行 | 200,000 |
| 足球稿 | 10,645 |
| 规则粗筛赛果 | 1,018 |
| Qwen 保留赛果 | 558（55%） |
| 博彩（隔离） | 203 |
