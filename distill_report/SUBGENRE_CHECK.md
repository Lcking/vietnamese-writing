# 第 4 条 子体裁校验

## 结论：本轮 20 个子体裁**全部为通用类，不含赛果/转会/人物等足球子体裁**

本轮的 20 个子体裁（category/sub）：

| category | 子体裁 |
|---|---|
| culture | literature, customs, art, religion |
| local_life | social, entertainment, cuisine, travel, work |
| history_policy | history, geography, heritage, military |
| professional_field | institutions, medicine, finance, technology, academic, law, education |

**没有任何一个匹配以下足球子体裁规则**（本脚本 `SUB_RULES` 内）：

- `ket_qua`（赛果）：需有比分 + 进球分钟/比分动词
- `chuyen_nhuong`（转会）：chuyển nhượng / ký hợp đồng / chiêu mộ / gia nhập
- `nhan_dinh`（赛前）：nhận định / trước trận / soi kèo / dự đoán
- `phong_van`（人物/访谈）：phát biểu / chia sẻ / cho biết

因此**本报告无数据**：校验规则已实现，但当前无适用对象。
待第二阶段摸底确认足球素材量后，第三阶段抽取的足球稿才会用到这些规则。

## 校验规则（实现于 `bin/postprocess_distill.py: SUB_RULES`）

| 子体裁 | 判定条件 |
|---|---|
| ket_qua | 有 `\d+-\d+` **且**（有 `phút \d+` 或 `\d+'` **或** 有比分动词 mở tỷ số/gỡ hòa/nâng tỷ số/rút ngắn cách biệt/vượt lên dẫn/san bằng/ấn định） |
| chuyen_nhuong | chuyển nhượng / ký hợp đồng / chiêu mộ / gia nhập / rời CLB / thương vụ / phí |
| nhan_dinh | nhận định / trước trận / soi kèo / dự đoán / sẽ gặp / phân tích / lực lượng / phong độ |
| phong_van | phát biểu / chia sẻ / cho biết / phỏng vấn / tuyên bố / trả lời |

## ngram 文件的来源更正

`ngram_ket_qua.tsv` **名不副实**，需更正：

- 该文件实际由**通用池**算出（因无 ket_qua 子体裁，脚本回退到通用候选池）
- 内容是最常见的 2–4 词短语（如 "việt nam"、"tổ chức"），**与赛果报道无关**
- 处理：**改名为 `ngram_generic.tsv`**；赛果专用版待第三阶段足球素材产出后另算
  （命名 `ngram_football_ket_qua.tsv`）

`entity_names.tsv` 同理，是通用名称表，与足球无关。
