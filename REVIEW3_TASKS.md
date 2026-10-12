# 第三轮评审整改任务清单（v1.4.1 更新）

基线：72fddeb → 当前 dd7ffd0+（v1.4.0）
评审：claude v3（第三轮）+ claude v3 复审（边界用例）

## 阶段 A：规则内容重写
- [x] A1 每体裁可执行规则卡（4 张，≤1500 字符，无汉字）—— 有测试卡长度
- [x] A2 清理长文件语气/旧例子（情绪词、Aubameyang/De Ligt/Lebanon 已改抽象句式）
- [x] A3 lite 只读卡片；无卡片报告 card_missing

## 阶段 B：确定性能力
- [x] B1 事实预处理 prepare_facts.py —— **复审修 3 处核心错误**：
      - 落后方进球→rút ngắn cách biệt（原误报 nâng tỷ số）
      - 决胜事件：1-0/2-0 有值；反复反超取最后一次
      - 补时 45+2 不崩溃；两乌龙不算梅开二度
- [x] B2 风格检查 check_style.py（S1-S9）—— 复审修 4 处误报：
      - S3 不再把 ghi bàn 当预告；S4 积分榜结尾不算复述
      - S6 全队两黄不报、正则不重叠；S8 去掉 định đoạt
- [x] B3 --revise 修订后**再检查一次**并保存；仅实质问题触发（S8 不触发）
- [x] B4 --length 篇幅合同

## 阶段 C：范文与提示
- [x] C1 范文只选**人工确认**（type_reviewed=True）；无可选→0 条并报告
- [x] C2 蒸馏分数定性为排序参考（文档）
- [x] C3 --model-tier small|large：small=卡片+无范文+无全局规则+需 facts+建议 revise
- [x] 提示无汉字（卡片说明行注入前剥离；msg 全越南语）
- [x] 规则文件无回归样本事实泄漏

## 阶段 D：评测与工程
- [x] D1 赛果评测组 G1-G4，**传 facts**（S1/S9 真正运行）
- [x] D2 编辑记录框架（eval/editor_edits/）
- [x] 工程：distill_work/ 移出仓库（.gitignore）；GENERIC_MAP 缺失范文报告；lich_su.md 保留

## 复审第三轮（claude v3）已修
- [x] 1 S6 用 facts 判第二黄：句中含 second_yellow 球员名即报（单独句也报），全队两黄不报
- [x] 2 事实块补全：红黄牌进"比赛进程"（无分钟标 không rõ phút）、标题候选单列、缺项名越南语
- [x] 3 乌龙球决胜：写成"phản lưới nhà của X → 有利益方"，标题聚焦受益方
- [x] 4 final 与事件不一致 → 明确警告并停用胜负推导
- [x] 5 45+2 计入半场比分；点球大战识别胜方
- [x] 6 run_eval 生成阶段注入事实块；G1 facts 改为读文件
- [x] 7 model-tier small 真正生效（自动开启风格检查修订）
- [x] 8 回归样本补齐 input_original.txt + expected_issues.json
- [ ] 9 git 历史里的 77MB 语料（工作树已移除；如需重写历史另议）
- C1 补：--allow-unreviewed-examples 显式开关（默认关）+ 人工确认小集（待编辑）

## 复审第四轮（claude v3）已修

- [x] 1 乌龙球标题线索一致:title_candidates 与 S9 同规则处理乌龙球
- [x] 2 点球大战事实块带比分(4-3);去掉开发者说明;平局靠点球时给出标题建议
- [x] 3 比分不一致时"逆转"也停用
- [x] 4 未提供 final → 提示"tỷ số chung cuộc không được cung cấp"并停用胜负推断
- [x] 5 有进球缺分钟 → 不给动词/决胜球,只列事实 + 警告
- [x] 6 team 支持队名映射,映射不上报错(不再静默当客队)
- [x] 7 同队多张红牌合并为"thiếu N người"
- [x] 8 点球进球标 (phạt đền);罚丢点球单列
- [x] 9 S6 按名字后缀匹配(全名/后两音节)
- [x] 规则调整:S6 降级为提示(hint_only),S2/S3/S4/S7 同样只提示不自动修订;
      small 档自动修订只在 S1/S5/S9(确定性判断)触发
- [x] --allow-unreviewed-examples 在 dump 显示"đang dùng ví dụ CHƯA duyệt"
- [x] run_eval 三组对照:raw / skill(规则卡,不注 facts) / full(规则卡+facts)
- [x] 测试数核对:实测 59 例(35+15+9),此前"50 例"是误报

## 仍需母语编辑（无法自动）
- [ ] C2 编辑抽检 20 篇
- [ ] D2 真实编辑改稿记录
- [ ] 母语盲评

## 测试状态
- test_prepare_facts.py: 19 例（含复审 6 边界场景）
- test_check_style.py: 13 例（含复审 4 误报 + 卡片长度）
- test_check_fabrication.py: 9 例
- 共 41 例，全过；check_quality 17 项 0 问题
