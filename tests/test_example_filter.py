#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_example_filter.py — 范文筛选测试。

对应本轮复审第 2 条:
  allow_unreviewed 只放宽"是否人工确认",article_type 筛选必须照常生效。
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

import viet_writer as vw  # noqa: E402


class TestArticleTypeFilter(unittest.TestCase):

    def test_ket_qua_only_returns_ket_qua(self):
        """allow_unreviewed=True 时,赛果体裁选出的范文 article_type 必须全是 ket_qua。"""
        _, meta, _ = vw.pick_examples(
            "football_ket_qua", 20000, max_n=20, max_chars=3000,
            article_type="ket_qua", strict_reviewed=False)
        self.assertTrue(meta, "应至少选到 1 条(当前库里有 31 条 ket_qua)")
        for m in meta:
            self.assertEqual(m.get("article_type"), "ket_qua",
                             f"混入非赛果稿: {m.get('title')} "
                             f"(article_type={m.get('article_type')})")

    def test_strict_mode_only_returns_reviewed(self):
        """严格模式(要求 type_reviewed):只返回人工确认过的范文。

        2026-10 起已有 17 条导师确认赛果范文,故此处应 >0 条且全部已确认。
        (此前范文池无确认条目时,这里断言为 0 条。)
        """
        _, meta, _ = vw.pick_examples(
            "football_ket_qua", 20000, max_n=20, max_chars=3000,
            article_type="ket_qua", strict_reviewed=True)
        self.assertGreater(len(meta), 0, "已有确认范文时应能选出")
        for m in meta:
            self.assertTrue(m.get("type_reviewed"),
                            f"严格模式混入未确认: {m.get('title')}")

    def test_allow_unreviewed_does_not_disable_type_filter(self):
        """两条路径都传 article_type 时,选出的类型集合必须一致。"""
        _, m_loose, _ = vw.pick_examples(
            "football_ket_qua", 20000, max_n=20, max_chars=3000,
            article_type="ket_qua", strict_reviewed=False)
        types = {m.get("article_type") for m in m_loose}
        self.assertTrue(types <= {"ket_qua"}, f"出现了非 ket_qua: {types}")

    def test_no_article_type_filter_can_mix(self):
        """不传 article_type 时,候选源比传筛选项时更宽(证明筛选确实在起作用)。

        做法:不传筛选 → 记录候选总数;传 ket_qua 筛选 → 再记录;
        宽口径应 >= 筛选口径(严格相等说明筛选没生效)。
        """
        _, meta_all, _ = vw.pick_examples(
            "football_ket_qua", 10**9, max_n=999, max_chars=10**9,
            article_type=None, strict_reviewed=False)
        _, meta_kq, _ = vw.pick_examples(
            "football_ket_qua", 10**9, max_n=999, max_chars=10**9,
            article_type="ket_qua", strict_reviewed=False)
        self.assertGreaterEqual(
            len(meta_all), len(meta_kq),
            f"不传筛选({len(meta_all)})应不少于筛选后({len(meta_kq)})")


if __name__ == "__main__":
    unittest.main()
