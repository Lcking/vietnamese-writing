# 导师盲审范文种子（可入库）

`ket_qua_mentor_bt.jsonl`：6 篇赛果范文，来自 2026-10 越南语导师盲审。

- **来源**：E5 评测里模型生成的稿件（非 WanJuan 语料），无第三方正文版权问题。
- **筛选**：导师 `pub=co` 或 `sua_nho`，并只应用不引入编造的改句。
- **字段**：`type_reviewed=True`、`article_type=ket_qua`、`reviewed_by=human`。

WanJuan 语料确认范文仍走 `ket_qua_reviewed.jsonl`（gitignore + `hydrate_examples.py`），
需远端 `distill_work/` 恢复后才能生成。
