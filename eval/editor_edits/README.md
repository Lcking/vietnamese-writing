# 编辑改稿记录 (Editor edits)

用于把母语编辑的改稿沉淀成规则。

## 流程
1. 选约 20 篇不同体裁的输出(首稿)。
2. 请越南语编辑直接改成可发布稿。
3. 每条保存为一行 JSON(见 _TEMPLATE.json):
   id / genre / model / profile / input / draft / edited / editor_notes / date
4. 把高频改动整理成规则卡条目或 check_style 检查项,
   每条注明来源编辑记录的 id。

## 为什么重要
这是**最可靠的规则来源**——优先于语料提炼,因为它是真人编辑的实际判断。

## 现状
- 待母语编辑资源。目前 _TEMPLATE.json 就绪,尚未有真实记录。
- 本目录为空时,规则卡来自语料提炼 + 评审参考改写。
