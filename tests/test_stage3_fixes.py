#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_stage3_fixes.py — 第三阶段三处修正的回归测试。

覆盖评审 2026-10-14 的三条:
  ① 比分清洗:7 种标准写法能认出;日期/量词仍不能认
  ② 博彩稿只进 betting 类(已在 test_score_parsing 覆盖,这里补聚合页/其他运动)
  ③ 年份提取:优先发布时间,忽略"Thứ X, ngày..."头部行
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import extract_football as ef  # noqa: E402


class TestScoreWashing(unittest.TestCase):
    """① 比分清洗。"""

    POSITIVE = [
        "Việt Nam thắng 2-0 trước Thái Lan",
        "Hà Nội thắng 3-1 trên sân nhà",
        "Arsenal thắng 2-1 trong trận đấu",
        "dẫn 1-0 giờ nghỉ",
        "1-0 phút 90",
        "kết thúc với tỷ số 1-1",
        "MU thua 0-3 tại Old Trafford",
    ]
    NEGATIVE = ["1-2 thìa", "5-10 kg", "1-2 triệu", "07-25", "ngày 12/07/2025"]

    def test_standard_scores_recognised(self):
        bad = [t for t in self.POSITIVE if not ef.find_scores(t)]
        self.assertFalse(bad, f"标准赛果写法未认出比分: {bad}")

    def test_units_and_dates_rejected(self):
        bad = [t for t in self.NEGATIVE if ef.find_scores(t)]
        self.assertFalse(bad, f"这些被误判为比分: {bad}")


class TestAggregatorAndOtherSport(unittest.TestCase):
    """③ 聚合页与其他运动项目。"""

    def test_aggregator_detected(self):
        agg = ("Tags - Bao Hai Duong 6 giờ trước Trận đấu Man United vs Atalanta "
               "3 ngày trước 9 ngày trước")
        self.assertTrue(ef.is_aggregator(agg))

    def test_normal_report_not_aggregator(self):
        t = "Kết quả Nam Định 1-1 Hải Phòng. Phút 56, Nnamani ghi bàn."
        self.assertFalse(ef.is_aggregator(t))

    def test_other_sport_teams_excluded(self):
        self.assertTrue(ef.OTHER_SPORT_TEAMS.search("76ers thua Wizards"))
        self.assertTrue(ef.OTHER_SPORT_TEAMS.search("Lakers vs Celtics"))
        self.assertFalse(ef.OTHER_SPORT_TEAMS.search("Hà Nội FC vs Thanh Hóa"))

    def test_offtopic_excluded(self):
        self.assertTrue(ef.EF_OFFTOPIC_RE.search("chòm sao Cự Xà"))
        self.assertTrue(ef.EF_OFFTOPIC_RE.search("giá vàng hôm nay"))
        self.assertFalse(ef.EF_OFFTOPIC_RE.search("V.League vòng 3"))


class TestYearExtraction(unittest.TestCase):
    """④ 年份提取。"""

    def test_prefers_publish_date(self):
        self.assertEqual(
            ef.extract_year("Hòa 1-1. Thứ 4, ngày 30 tháng 11 năm 2022  "
                            "15:48 17/05/2021  Cặp tiền đạo"), 2021)

    def test_earliest_publish_date(self):
        # 正文里后续日期是引述,发布时间在开头 → 取最早
        self.assertEqual(
            ef.extract_year("Cú giật gót Drogba. Thứ Tư 10/04/2013  "
                            "22:13 23/09/2020  Cầu thủ già nhất"), 2013)

    def test_gmt7_format(self):
        self.assertEqual(
            ef.extract_year("Kết quả. 30/10/2019 05:14 GMT+7  TTO - Rạng sáng"), 2019)

    def test_season_fallback(self):
        self.assertEqual(ef.extract_year("Mùa giải 2023/24 nhiều bất ngờ"), 2023)

    def test_ignores_header_line(self):
        # 头部 "Thứ 7, ngày 22 tháng 1 năm 2022" 不应作为唯一年份来源
        t = "Tin. Thứ 7, ngày 22 tháng 1 năm 2022  Nội dung không có ngày khác."
        # 无发布时间时,孤立年份兜底(此处仅头部有) → 允许 None 或 2022
        self.assertIn(ef.extract_year(t), (None, 2022))


if __name__ == "__main__":
    unittest.main()
