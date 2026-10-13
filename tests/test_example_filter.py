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

    def test_strict_mode_returns_zero_without_reviewed(self):
        """严格模式(要求 type_reviewed):当前库里无人确认 → 应注入 0 条,不拿别类型凑数。"""
        _, meta, _ = vw.pick_examples(
            "football_ket_qua", 20000, max_n=20, max_chars=3000,
            article_type="ket_qua", strict_reviewed=True)
        self.assertEqual(meta, [], "无人确认时不应注入任何范文")

    def test_allow_unreviewed_does_not_disable_type_filter(self):
        """两条路径都传 article_type 时,选出的类型集合必须一致。"""
        _, m_loose, _ = vw.pick_examples(
            "football_ket_qua", 20000, max_n=20, max_chars=3000,
            article_type="ket_qua", strict_reviewed=False)
        types = {m.get("article_type") for m in m_loose}
        self.assertTrue(types <= {"ket_qua"}, f"出现了非 ket_qua: {types}")

    def test_no_article_type_filter_keeps_mixed(self):
        """不传 article_type 时会混入其他类型(对照,证明筛选确实起作用)。"""
        _, meta, _ = vw.pick_examples(
            "football_ket_qua", 20000, max_n=30, max_chars=3000,
            article_type=None, strict_reviewed=False)
        types = {m.get("article_type") for m in meta}
        self.assertTrue(len(types) > 1 or None in types or types != {"ket_qua"},
                        f"未传筛选却只出现单一类型,筛选可能失效: {types}")


if __name__ == "__main__":
    unittest.main()
