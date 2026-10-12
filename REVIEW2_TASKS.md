# 二次评审任务清单（claude 评审 → 落地执行）

优先级：事实分层与检测 > 精简提示 > 语料质量 > 评测与文档
验证状态：评审全部指控已在本机复现属实（T1/T2/T4/T5 均复现）。

## 阶段一：事实边界（P0）✅ 完成
- [x] 1.1 prompts/system_vi_writer.md：加「事实分层三分类 + 两条禁止」；成语移出核心；「只返回正文」改为合同优先 —— 验收通过（"Chỉ trả về nội dung" 0 次、事实分层在、核心无 thành ngữ）
- [x] 1.2 bin/check_fabrication.py：否定作用域限同句；新增「状态断言」类；新增「因果连接」类；归一化（破折号/日期/数字词/được）
- [x] 1.2b tests/test_check_fabrication.py：T1–T9 全部通过
- [x] 1.3 eval/evalset.md + bin/run_eval.py：补 3 个「缺项应省略」用例（待做，见下）
- 疑点对比：旧检测器 31/97 → 新检测器 54/97（新增状态断言+因果两类，覆盖更广）

## 阶段二：精简默认提示（P1）
- [ ] 2.1 bin/viet_writer.py：新增 --profile min/lite/full；social_post & football_tin_tuc 默认 lite；修正 stats
- [ ] 2.2 pick_examples()：post_type 参数；去 content[:1500] 硬截；排除过旧条目；加 [Mẫu diễn đạt – không phải dữ kiện]
- [ ] 2.3 src/llm_client.py：捕获 timeout（kind=timeout，不重试）；5xx 默认重试 1 次；修 learned.values() 恒真 bug

## 阶段三：规则与语料质量（P0）
- [ ] 3.1 references/_global_gioi_tu_tro.md 四处修正；football_binh_luan.md 删中文注释；加汉字检查；_global_*.md 标 review_status
- [ ] 3.2 重建 social_post 语料：非足球词表过滤、噪声正则、标题正文一致性、type_reviewed；其他 8 主题同过滤

## 阶段四：评测与文档（P2）
- [ ] 4.1 母语盲评（需真人，无法自动完成）
- [ ] 4.2 run_eval.py 每条附检测器输出；报告分列「规则命中」与「事实疑点」
- [ ] 4.3 SKILL.md 更新（体裁表/范文数/目录/--profile）
- [ ] 4.4 CHANGELOG / README 版本段

## 验收（评审要求）
- 1.1: --dump-prompt --format 后 system prompt 无「Chỉ trả về nội dung bài viết」
- 1.2: T1–T9 全过；--scan-eval 前后疑点数对比
- 2.1: --dump-prompt --genre social_post 显示 profile=lite 且 ≤5000 字符；--profile full 与 770bd56 一致
- 3.2: social_post.jsonl 非足球 0 条、噪声 0 条
