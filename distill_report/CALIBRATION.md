# 第 1 条 分数校准

各子体裁 top 500 的 q_score 分布(用于判断 7.0 卡线是否合理)。

| 子体裁 | N | min | p10 | 中位 | p90 | max | 7.0±0.2 条数 | 标定表 |
|---|---|---|---|---|---|---|---|---|
| culture_art | 500 | 7.5 | 7.5 | 8.25 | 8.75 | 9.25 | 0 | calibration_culture_art.csv |
| culture_customs | 500 | 7.25 | 7.5 | 8.0 | 8.5 | 9.0 | 0 | calibration_culture_customs.csv |
| culture_literature | 500 | 7.25 | 7.5 | 8.25 | 8.75 | 9.25 | 0 | calibration_culture_literature.csv |
| culture_religion | 500 | 7.5 | 7.75 | 8.25 | 8.75 | 9.25 | 0 | calibration_culture_religion.csv |
| history_geography | 500 | 7.75 | 8.0 | 8.25 | 8.75 | 9.25 | 0 | calibration_history_geography.csv |
| history_heritage | 500 | 7.5 | 7.5 | 8.0 | 8.75 | 9.25 | 0 | calibration_history_heritage.csv |
| history_history | 500 | 7.25 | 7.5 | 8.0 | 8.5 | 9.25 | 0 | calibration_history_history.csv |
| history_military | 500 | 7.5 | 7.75 | 8.25 | 8.75 | 9.25 | 0 | calibration_history_military.csv |
| local_cuisine | 500 | 7.5 | 7.75 | 8.25 | 8.75 | 9.25 | 0 | calibration_local_cuisine.csv |
| local_entertainment | 500 | 7.5 | 7.5 | 8.0 | 8.5 | 9.25 | 0 | calibration_local_entertainment.csv |
| local_social | 500 | 7.75 | 7.75 | 8.25 | 8.75 | 9.25 | 0 | calibration_local_social.csv |
| local_travel | 500 | 7.5 | 7.5 | 8.25 | 8.75 | 9.25 | 0 | calibration_local_travel.csv |
| local_work | 500 | 7.75 | 7.75 | 8.25 | 8.75 | 9.25 | 0 | calibration_local_work.csv |
| prof_academic | 500 | 7.0 | 7.25 | 8.0 | 8.5 | 9.25 | 8 | calibration_prof_academic.csv |
| prof_education | 500 | 7.0 | 7.25 | 8.0 | 8.5 | 9.0 | 30 | calibration_prof_education.csv |
| prof_finance | 500 | 7.75 | 8.0 | 8.25 | 9.0 | 9.25 | 0 | calibration_prof_finance.csv |
| prof_institutions | 500 | 7.5 | 7.5 | 8.25 | 8.75 | 9.25 | 0 | calibration_prof_institutions.csv |
| prof_law | 500 | 8.0 | 8.25 | 8.5 | 9.0 | 9.25 | 0 | calibration_prof_law.csv |
| prof_medicine | 500 | 7.5 | 7.75 | 8.25 | 8.75 | 9.25 | 0 | calibration_prof_medicine.csv |
| prof_technology | 500 | 7.5 | 7.5 | 8.25 | 8.75 | 9.25 | 0 | calibration_prof_technology.csv |

## 说明

- 标定表每子体裁含 high/mid/low 各 10 条,供人工判好/中/差。
- 人工判完后,计算与 q_score 的一致性(能否分开好与差)。
- 若分不开:入库标准改为'硬过滤后的分数前 N 条',报告中注明分数只用于排序。