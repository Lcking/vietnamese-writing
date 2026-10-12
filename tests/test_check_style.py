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
import re
import pathlib as _pl
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

    # S1: nâng tỷ số là nhãn chính cho 1-3 → 零命中
    def test_s1_primary_label_nang_ty_so(self):
        issues = check("Phút 64, Passira nâng tỷ số lên 1-3 cho Hà Tĩnh.", self.facts)
        self.assertNotIn("S1", {i["rule"] for i in issues},
                         "nâng tỷ số 1-3 是主标签,不应报 S1")

    # S1: nhân đôi cách biệt 在领先 1→2 时可接受 → 零命中
    def test_s1_accepted_alt_nhan_doi(self):
        issues = check("Phút 64, Passira nhân đôi cách biệt lên 1-3 cho Hà Tĩnh.", self.facts)
        self.assertNotIn("S1", {i["rule"] for i in issues},
                         "1-3(领先1→2)用 nhân đôi cách biệt 是可接受替代,不应报 S1")

    # S1: 领先未翻倍却用 nhân đôi → 应报
    def test_s1_nhan_doi_wrong_when_not_doubling(self):
        facts3 = {"home": "A", "away": "B", "final": [3, 0], "events": [
            {"minute": 10, "type": "goal", "team": "home", "player": "P1"},
            {"minute": 20, "type": "goal", "team": "home", "player": "P2"},
            {"minute": 30, "type": "goal", "team": "home", "player": "P3"}]}
        issues = check("Phút 30, P3 nhân đôi cách biệt lên 3-0.", facts3)
        self.assertIn("S1", {i["rule"] for i in issues},
                      "2-0→3-0 领先未翻倍,用 nhân đôi cách biệt 应报 S1")

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
        issues = check("Quốc Dân nhận 2 thẻ vàng và bị truất quyền thi đấu.")
        self.assertIn("S6", {i["rule"] for i in issues})

    def test_s6_team_two_yellows_ok(self):
        """全队两张黄牌是正常写法,不该报 S6。"""
        issues = check("Hà Tĩnh nhận 2 thẻ vàng trong hiệp một.")
        self.assertNotIn("S6", {i["rule"] for i in issues})

    # S9:标题缺决胜球员 → 报
    def test_s9_missing_decider(self):
        text = "Thể Công thua Hà Tĩnh 1-3\n\nDiễn biến trận đấu..."
        issues = check(text, self.facts)
        self.assertIn("S9", {i["rule"] for i in issues})


class TestCards(unittest.TestCase):
    """A1 验收:每张卡 ≤1500 字符(含标记可略超,但须 <1700)、无汉字。"""

    CARDS_DIR = _pl.Path(__file__).resolve().parent.parent / "references/cards"

    def test_card_length_and_no_han(self):
        for fp in sorted(self.CARDS_DIR.glob("*.md")):
            txt = fp.read_text(encoding="utf-8")
            n = len(txt)
            # lite 卡 ≤1700;large 专用卡(线上模型,内容更全)≤3000
            limit = 3000 if fp.name.endswith("_large.md") else 1700
            self.assertLess(n, limit, f"{fp.name} 超长({n} 字符 > {limit})")
            han = re.findall(r"[\u4e00-\u9fff]+", txt)
            self.assertEqual(han, [], f"{fp.name} 含汉字: {han}")


class TestS6Suffix(unittest.TestCase):
    """S6 按名字后缀匹配(越南媒体常只写后两音节)。"""

    def test_s6_suffix_match(self):
        facts = {"home": "A", "away": "B", "final": [1, 0], "events": [
            {"minute": 10, "type": "goal", "team": "home", "player": "P"},
            {"minute": 30, "type": "second_yellow", "team": "away",
             "player": "Nguyễn Quốc Dân"}]}
        for s in ("Nguyễn Quốc Dân nhận 2 thẻ vàng.", "Quốc Dân nhận 2 thẻ vàng."):
            rules = {i["rule"] for i in check(s, facts)}
            self.assertIn("S6", rules, f"'{s}' 应命中 S6")

    def test_s6_is_hint_only(self):
        """S6 是提示级(hint_only),不触发自动修订。"""
        facts = {"home": "A", "away": "B", "final": [1, 0], "events": [
            {"minute": 10, "type": "goal", "team": "home", "player": "P"},
            {"minute": 30, "type": "second_yellow", "team": "away",
             "player": "Nguyễn Quốc Dân"}]}
        hits = [i for i in check("Quốc Dân nhận 2 thẻ vàng.", facts) if i["rule"] == "S6"]
        self.assertTrue(hits and all(i.get("hint_only") for i in hits))


class TestS9OwnGoal(unittest.TestCase):
    """S9 应拦住以乌龙球员为主角的标题。"""

    FACTS = {"home": "Đội A", "away": "Đội B", "final": [0, 1],
             "events": [{"minute": 10, "type": "own_goal", "team": "home", "player": "Z"}]}

    def test_own_goal_player_as_headline(self):
        rules = {i["rule"] for i in check("Z tỏa sáng, Đội A thắng 2-1", self.FACTS)}
        self.assertIn("S9", rules)

    def test_beneficiary_headline_ok(self):
        rules = {i["rule"] for i in check("Đội B thắng nhờ phản lưới nhà", self.FACTS)}
        self.assertNotIn("S9", rules)


class TestRealRunIssues(unittest.TestCase):
    """v1.4.4 真实生成跑出的错误句(评审 evidence)作为回归用例。"""

    import pathlib as _p2

    def _facts(self, name):
        import json as _j
        fp = _pl.Path(__file__).resolve().parent.parent / "eval/regression/real_matches_20261012" / f"{name}.json"
        return _j.loads(fp.read_text(encoding="utf-8"))

    def test_braga_home_away_reversed(self):
        f = self._facts("M5_braga_sporting")
        rules = {i["rule"] for i in check("Sporting đón tiếp Braga tại nhà", f)}
        self.assertIn("S13", rules)

    def test_red_card_wrong_team(self):
        f = self._facts("M4_dong_nai_binh_minh")
        rules = {i["rule"] for i in check("Chiếc thẻ đỏ buộc đội chủ nhà phải chơi thiếu người", f)}
        self.assertIn("S13", rules)

    def test_time_word_mismatch(self):
        f = self._facts("M5_braga_sporting")
        rules = {i["rule"] for i in check("Phút 57, đội khách có bàn gỡ hòa trong phút cuối", f)}
        self.assertIn("S12", rules)

    def test_han_characters_blocking(self):
        rules = {i["rule"] for i in check("Anh lập大功 cho đội nhà")}
        self.assertIn("S10", rules)

    def test_markdown_residue_blocking(self):
        rules = {i["rule"] for i in check("Anh ghi bàn **vượt lên dẫn** cho đội khách")}
        self.assertIn("S11", rules)

    def test_fabricated_coach(self):
        f = self._facts("M5_braga_sporting")
        rules = {i["rule"] for i in check("HLV Nguyễn Văn Thắng cho biết đội sẽ cố gắng", f)}
        self.assertIn("S14", rules)

    def test_no_false_positive_cup_quoc_gia(self):
        """'Cúp Quốc gia' 里的 Quốc 不该被当球员名(评审 M4 误报)。"""
        f = self._facts("M4_dong_nai_binh_minh")
        msgs = " ".join(i["msg"] for i in check("TP. Đồng Nai 4-3 Bình Minh Sài Gòn", f))
        self.assertNotIn("Quốc", msgs)


class TestE4RegressionTable(unittest.TestCase):
    """E4 回归表:评审 evidence 里的真实错误句 → 必须报/不能报。"""

    import pathlib as _p3

    def _f(self, name):
        import json as _j
        fp = _pl.Path(__file__).resolve().parent.parent /             "eval/regression/real_matches_20261012" / f"{name}.json"
        return _j.loads(fp.read_text(encoding="utf-8"))

    def test_qwen_M1_rules_text_must_report(self):
        f = self._f("M1_hai_phong_thanh_hoa")
        rules = {i["rule"] for i in check("HLV Nguyễn Văn Thắng nói đội sẽ cố gắng.", f)}
        self.assertIn("S14", rules)

    def test_qwen_M1_factblock_must_report(self):
        f = self._f("M1_hai_phong_thanh_hoa")
        txt = "Phút 57, đội khách gỡ hòa trong những phút cuối trận. Thanh Hóa thắng với tỷ số 1-2."
        rules = {i["rule"] for i in check(txt, f)}
        self.assertIn("S12", rules)
        self.assertIn("S15", rules)

    def test_qwen_M4_rules_text_must_report(self):
        f = self._f("M4_dong_nai_binh_minh")
        rules = {i["rule"] for i in check("Phút 64 mở tỷ số ngay trong hiệp một, anh lập大功.", f)}
        self.assertIn("S10", rules)
        self.assertIn("S12", rules)

    def test_qwen_M5_rules_text_must_report(self):
        f = self._f("M5_braga_sporting")
        txt = ("Trận hòa giữa Braga và Sporting, 1-3 nghiêng về phía chủ nhà. "
               "cú đúp của Luis Suarez. Rodrigo Zalazar lập bàn thắng quyết định.")
        rules = {i["rule"] for i in check(txt, f)}
        for r in ("S15", "S16", "S17"):
            self.assertIn(r, rules)

    def test_grok_M5_factblock_clean(self):
        """grok M5 事实块组:同样的正确稿不该报 S1(顺序不可靠时跳过)。"""
        f = self._f("M5_braga_sporting")
        clean = ("Sporting thắng Braga 3-1. Bernardo mở tỷ số cho Sporting, "
                 "Rui Silva phản lưới nhà giúp Sporting, Zalazar phản lưới nhà giúp Braga, "
                 "Suárez ấn định tỷ số.")
        rules = {i["rule"] for i in check(clean, f)}
        self.assertNotIn("S1", rules)

    def test_grok_M3_meta_sentence(self):
        f = self._f("M3_ha_noi_da_nang_pen")
        rules = {i["rule"] for i in check("Tỷ số 4-3 là kết quả loạt luân lưu, không phải tỷ số trong 90 phút.", f)}
        self.assertIn("S18", rules)


if __name__ == "__main__":
    unittest.main(verbosity=2)
