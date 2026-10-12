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

## 仍需母语编辑（无法自动）
- [ ] C2 编辑抽检 20 篇
- [ ] D2 真实编辑改稿记录
- [ ] 母语盲评

## 测试状态
- test_prepare_facts.py: 19 例（含复审 6 边界场景）
- test_check_style.py: 13 例（含复审 4 误报 + 卡片长度）
- test_check_fabrication.py: 9 例
- 共 41 例，全过；check_quality 17 项 0 问题
