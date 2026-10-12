# 第三轮评审任务清单（Claude review v3）

基线：72fddeb  核验状态：**E1-E7 全部 7 条属实**；情绪词/截断/范文错配 3 条核验属实。

## 核心诊断
skill 只提供"事实纪律"（不写错），未提供"体裁写作知识"（怎么写好）：
规则文件从语料机械提炼 → 缺可执行规范（比分动词、决胜事件判断、不重复、结尾处理）。

## 贯穿样本
- [ ] R1 eval/regression/the_cong_ha_tinh_20261008/：input_original.txt / facts.json /
      output_qwen27b_lite_72fddeb.txt（反例）/ expected_issues.json（E1-E7）

## 阶段 A：重写规则内容（最高优先）
- [ ] A1 references/cards/ 新增"可执行规则卡"（≤1500字符，不截断）
      第一批：ket_qua_tran / chuyen_nhuong / nhan_dinh_truoc_tran / social_post
      新增 football_ket_qua 体裁；lite 只注卡片
- [ ] A2 清理 football_tin_tuc.md：删情绪词推荐(第51/55行)、旧例子改抽象句式
- [ ] A3 lite 不再在节中间截断长文件；无卡片体裁报 card_missing

## 阶段 B：确定性能力
- [ ] B1 bin/prepare_facts.py：事实预处理（推算比分动词/决胜事件/冗余/缺项/输入纠错）
      viet_writer 加 --facts；验证：mở tỷ số 0-1、gỡ hòa 1-1、vượt lên dẫn 1-2、
      nâng tỷ số 1-3+cú đúp、决胜=60'Passira、round/venue/红牌分钟=absent
- [ ] B2 bin/check_style.py：S1-S9 风格检查（比分动词矛盾/重复比分/先预告再展开/
      结尾复述/内部描述/纪律术语/情绪词密度/待审搭配/标题决胜事件）
      验证：回归样本命中 E1-E7；参考改写零命中
- [ ] B3 --revise 可选修订一次（默认关）
- [ ] B4 --length 500-900 篇幅合同

## 阶段 C：范文与模型档次
- [ ] C1 范文加 article_type(ket_qua/chuyen_nhuong/...) + type_reviewed；按类型匹配
- [ ] C2 蒸馏分数用途写明为"排序参考"，非质量证明；请编辑抽 30 条判定一致率
- [ ] C3 --model-tier small|large（small=卡片+预处理+1-2范文，不注全局规则）

## 阶段 D：评测与编辑闭环
- [ ] D1 evalset 补赛果组（回归/逆转/平局/红牌少打一人获胜）
- [ ] D2 编辑改稿记录 eval/editor_edits/*.jsonl → 反哺规则卡

## 优先级
1) A1 A2 A3 B1 B2（决定赛果稿能否写对）
2) B4 C1 C3 D1（验证效果）
3) B3 C2 D2（配合母语编辑）

## 交付
各阶段 commit hash；--dump-prompt 完整输出；测试日志；回归样本新版输出+B2结果；
C1 类型统计；D2 编辑记录。
