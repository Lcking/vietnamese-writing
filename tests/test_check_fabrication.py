#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tests/test_check_fabrication.py — Bộ kiểm thử cho detector dữ kiện bịa.

Chạy:  python -m pytest tests/ -q      hoặc      python tests/test_check_fabrication.py

T1-T9 theo yêu cầu đánh giá vòng 2 (Claude review).
Tất cả các mảnh trong cột "output" đều là dữ kiện KHÔNG có trong đề bài.
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

from check_fabrication import find_fabrications  # noqa: E402


def hit_groups(task, text):
    return {f["nhóm"] for f in find_fabrications(task, text)}


def hit_frags(task, text):
    return {f["khớp"].lower() for f in find_fabrications(task, text)}


class TestFabrication(unittest.TestCase):
    # T1 — trạng thái khẳng định ("chưa được công bố") phải bị ĐÁNH DẤU
    def test_T1_status_assertion_flagged(self):
        task = "Bản tin về trận chung kết. (Chưa có dữ liệu về đối thủ.)"
        text = "Thông tin về đối thủ ở trận chung kết chưa được công bố."
        groups = hit_groups(task, text)
        self.assertTrue(any("trạng thái" in g for g in groups),
                        f"T1: phải bắt nhóm trạng thái, nhận {groups}")

    # T2 — quan hệ nhân quả bịa ("do bị đau...") phải bị ĐÁNH DẤU
    def test_T2_causal_flagged(self):
        task = "Anh rời sân ở phút 58. CLB thông báo anh bị đau cổ chân phải."
        text = "Anh rời sân ở phút 58 do bị đau cổ chân phải."
        groups = hit_groups(task, text)
        self.assertIn("quan hệ nhân quả", groups, f"T2: phải bắt nhân quả, nhận {groups}")

    # T3 — hai câu tách biệt, không nối nhân quả → KHÔNG đánh dấu nhân quả
    def test_T3_separate_sentences_not_flagged(self):
        task = "Anh rời sân ở phút 58. CLB thông báo anh bị đau cổ chân phải."
        text = "Anh rời sân ở phút 58. CLB thông báo anh bị đau cổ chân phải."
        frags = hit_frags(task, text)
        # 'do' không xuất hiện → không có nhân quả; các mảnh đều có trong đề
        self.assertNotIn("do", frags, f"T3: không nên bắt 'do', nhận {frags}")
        groups = hit_groups(task, text)
        self.assertNotIn("quan hệ nhân quả", groups, f"T3: nhận {groups}")

    # T4 — câu trước có phủ định KHÔNG được che câu sau (phạm vi cùng câu)
    def test_T4_negation_scope_same_sentence(self):
        task = "Cầu thủ chưa ra sân."
        text = "Anh chưa ra sân. Anh đã ký hợp đồng hai năm."
        frags = hit_frags(task, text)
        self.assertTrue(any("ký" in f for f in frags),
                        f"T4: phải bắt 'đã ký', nhận {frags}")

    # T5 — tỉ số 2–0 (gạch ngang dài) tương đương 2-0 → KHÔNG đánh dấu
    def test_T5_score_dash_normalized(self):
        task = "Đội nhà thắng 2-0."
        text = "Đội nhà thắng 2–0."
        self.assertEqual(find_fabrications(task, text), [],
                         "T5: 2–0 phải tương đương 2-0")

    # T6 — ngày 03/12 tương đương 3/12 → KHÔNG đánh dấu
    def test_T6_date_leading_zero_normalized(self):
        task = "Trận đấu ngày 3/12."
        text = "Trận đấu ngày 03/12."
        self.assertEqual(find_fabrications(task, text), [],
                         "T6: 03/12 phải tương đương 3/12")

    # T7 — số chữ "bốn trận" tương đương "4 trận" → KHÔNG đánh dấu
    def test_T7_digit_word_normalized(self):
        task = "Đội đã thắng 4 trận."
        text = "Đội đã thắng bốn trận."
        self.assertEqual(find_fabrications(task, text), [],
                         "T7: 'bốn trận' phải tương đương '4 trận'")

    # T8 — nguồn nói "chưa xác nhận" thì đầu ra giữ trạng thái đó → KHÔNG đánh dấu
    def test_T8_source_says_unconfirmed_not_flagged(self):
        task = "Nguồn tin cho biết thông tin này chưa xác nhận."
        text = "Thông tin này chưa được xác nhận."
        self.assertEqual(find_fabrications(task, text), [],
                         "T8: đề đã có 'chưa xác nhận' thì đầu ra không tính là bịa")

    # T9 — bối cảnh sân đấu bịa ("khán đài rộn ràng") → ĐÁNH DẤU
    def test_T9_stadium_context_flagged(self):
        task = "Tường thuật trận đấu: đội nhà thắng 1-0."
        text = "Đội nhà thắng 1-0 trong tiếng reo vang, khán đài rộn ràng."
        groups = hit_groups(task, text)
        self.assertIn("bối cảnh sân đấu / khán giả", groups,
                      f"T9: phải bắt bối cảnh sân đấu, nhận {groups}")


if __name__ == "__main__":
    unittest.main(verbosity=2)
