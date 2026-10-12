#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_check_style.py — 风格检查器测试。

运行: python -m pytest tests/ -q   或   python tests/test_check_style.py

关键断言(第三轮评审要求):
  - 回归样本(72fddeb 输出)命中 E1-E7 对应规则
  - 评审的参考改写零命中(除 S8 待审提示)
  - 反例:S2/S3/S4 不误报正常写法
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
from check_style import check  # noqa: E402

REG = ROOT / "eval/regression/the_cong_ha_tinh_20261008"


def rules_of(issues, exclude=("S8",)):
    return {i["rule"] for i in issues if i["rule"] not in exclude}


class TestCheckStyle(unittest.TestCase):
    def setUp(self):
        self.facts = json.loads((REG / "facts.json").read_text(encoding="utf-8"))
        self.bad = (REG / "output_qwen27b_lite_72fddeb.txt").read_text(encoding="utf-8")
        self.good = (REG / "expected_rewrite.txt").read_text(encoding="utf-8")

    # 回归样本应命中 E1-E7 对应的规则
    def test_regression_catches_e1_e7(self):
        issues = check(self.bad, self.facts)
        got = rules_of(issues)
        # E2 比分动词→S1; E3 先预告→S3; E4 重复比分→S2;
        # E5 结尾复述→S4; E6 内部描述→S5; E7 纪律→S6; E1 标题→S9
        for r in ("S1", "S2", "S3", "S4", "S5", "S6", "S9"):
            self.assertIn(r, got, f"回归样本应命中 {r},实际 {got}")

    # 参考改写零命中(除 S8 待审提示)
    def test_reference_rewrite_clean(self):
        issues = check(self.good, self.facts)
        got = rules_of(issues)
        self.assertEqual(got, set(), f"参考改写应零命中(除S8),实际 {got}")

    # S2 反例:比分只出现一次(或分处导语和不同事件) → 不算重复
    def test_s2_no_false_positive_single_occurrence(self):
        text = ("Đội A thắng 3-1 trước đội B.\n\n"
                "Phút 10, cầu thủ X mở tỷ số. Phút 20, cầu thủ Y nhân đôi cách biệt. "
                "Đội B gỡ lại một bàn ở phút 70 nhưng không thể san bằng.")
        issues = check(text)
        self.assertNotIn("S2", {i["rule"] for i in issues},
                         "比分只在导语出现一次,不应报 S2")

    # S3 反例:正常的时间顺序叙述 → 不报"先预告再展开"
    def test_s3_no_false_positive_chronological(self):
        text = ("Trận đấu diễn ra sôi nổi.\n\n"
                "Phút 16, Luiz Antonio mở tỷ số bằng cú sút xa.\n"
                "Phút 33, Khuất Văn Khang gỡ hòa 1-1.")
        issues = check(text)
        self.assertNotIn("S3", {i["rule"] for i in issues},
                         "正常按分钟叙述不应报 S3")

    # S4 反例:结尾有新信息(不是复述) → 不报
    def test_s4_no_false_positive_new_info(self):
        text = ("Đội A thắng 2-0.\n\n"
                "Phút 10 và 30, đội A ghi bàn.\n"
                "Thất bại khiến đội B tụt xuống vị trí cuối bảng với 3 điểm sau 5 vòng.")
        issues = check(text)
        self.assertNotIn("S4", {i["rule"] for i in issues},
                         "结尾含新信息不应报 S4")

    # S5:内部描述必报
    def test_s5_internal(self):
        issues = check("Trận đấu thuộc vòng mới nhất của V-League.")
        self.assertIn("S5", {i["rule"] for i in issues})

    # S6:纪律术语必报
    def test_s6_discipline(self):
        issues = check("Cầu thủ nhận 2 thẻ vàng và phải rời sân.")
        self.assertIn("S6", {i["rule"] for i in issues})

    # S9:标题缺决胜球员 → 报
    def test_s9_missing_decider(self):
        text = "Thể Công thua Hà Tĩnh 1-3\n\nDiễn biến trận đấu..."
        issues = check(text, self.facts)
        self.assertIn("S9", {i["rule"] for i in issues})


if __name__ == "__main__":
    unittest.main(verbosity=2)
