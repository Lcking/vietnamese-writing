# 第 9 条 范文池对照实验 —— 首轮无效

**结论：首轮实验无效，不采信。** 以下是原因与后续安排。

## 为什么无效

| # | 问题 | 事实 |
|---|---|---|
| 1 | 两组提示长度差异巨大 | 3,473 字符 vs 36,865 字符（10.6 倍）——差异不止"范文"，是两套不同档位 |
| 2 | 注入的范文不是赛果稿 | 6 条全部来自 `world_cup/ngoai_hang`，内容为 MU 进球榜、Ten Hag、Neymar 等，**均非赛果报道** |
| 3 | 范文非蒸馏产物 | 来自早期 `examples/football/`，与本次 20 子体裁蒸馏无关 |
| 4 | 报告写的档位没生效 | 脚本未把 `model_tier` 真正传给 `vw.write`，实际跑的是默认档 |
| 5 | 样本过小 | 两组各仅 9 篇 |

## 根因

- **A/B 不同档位**：A 用 `lite`（范文预算 0），B 用 `full`（预算 >0）。
  真正的纯对照必须在**同档位**下只切"范文开关"。
- **范文未确认且类型不匹配**：库里 `type_reviewed` 全为 False；
  `article_type` 是启发式标注（已证实不可靠——MU 进球榜被标成 ket_qua）。
- **脚本缺陷**：`model_tier` 未透传 → 已在本轮（第一阶段第 3 条）修复。

## 已修复（脚本层面）

- `model_tier` 现在真正传给 `vw.write`
- 两组改为**同档位**（都 `full`），唯一差别是 `allow_unreviewed` 开关
- `results.json` 新增字段：`system_chars`、`examples`（含每条范文的 title/article_type）、`rep`
- 新增 `--repeat N`（默认 3）与 API 端点支持
- 范文筛选补测试：赛果体裁选出的 `article_type` 必须全是 `ket_qua`；无则注入 0 条

## 为什么不现在重跑

纯对照需要**人工确认过的赛果范文**，而这批范文要等**第三阶段**产出。
当前库里：
- `type_reviewed=True` 的范文：**0 条**
- 启发式标为 ket_qua 且内容确实是赛果稿的：需人工确认后才可用

## 后续（第三阶段产出确认范文后）

```
VIET_LLM_DISABLE_THINKING=1 python bin/example_ab_test.py --repeat 3 --out eval/results/ab_examples
```

判据：阻断级问题数 + 小规模盲审。只有注入范文组**明显更好**才默认开启；
否则范文池仅用于产出统计资产。
