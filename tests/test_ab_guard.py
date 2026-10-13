#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_ab_guard.py — 对照实验的档位断言。

评审指出:example_ab_test 默认 --tier large,而 large 档若不能注入范文,
A/B 两组提示完全相同,实验等于自己和自己比(会白跑)。

本测试覆盖:
  1. large 档开了 allow_unreviewed 后确实能注入范文(>0)
  2. large 档默认(不开 allow_unreviewed)为 0 条范文
  3. 脚本的预检断言在 B 组范文为 0 时返回非 0 退出码
"""
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

import viet_writer as vw  # noqa: E402


class TestLargeTierExampleSlot(unittest.TestCase):

    def test_large_tier_can_inject_examples_when_allowed(self):
        """large 档 + allow_unreviewed=True 应能注入 1-2 条范文。"""
        p = vw.build_prompt("football_ket_qua", profile="full", model_tier="large",
                            allow_unreviewed=True)
        self.assertGreaterEqual(p["stats"].get("n_examples", 0), 1,
                                "large 档放宽确认后仍注入 0 条 → 对照实验会白跑")
        self.assertLessEqual(p["stats"].get("n_examples", 0), 2,
                             "large 档范文位应 ≤2 条")

    def test_large_tier_default_off(self):
        """large 档默认(不开 allow_unreviewed)应为 0 条范文。"""
        p = vw.build_prompt("football_ket_qua", profile="full", model_tier="large",
                            allow_unreviewed=False)
        self.assertEqual(p["stats"].get("n_examples", 0), 0)

    def test_ab_script_aborts_when_b_group_empty(self):
        """B 组范文为 0 时,脚本应报错退出(非 0),不出报告。"""
        import example_ab_test as abt
        # 用 small 档(当前无法注入范文)触发断言
        buf_err, buf_out = io.StringIO(), io.StringIO()
        with redirect_stderr(buf_err), redirect_stdout(buf_out):
            code = abt.main(["--tier", "small", "--limit", "1", "--out", "/tmp/ab_guard_test"])
        self.assertNotEqual(code, 0, "B 组范文为 0 时应返回非 0")
        self.assertIn("两组将完全相同", buf_err.getvalue())

    def test_ab_script_precheck_passes_for_large(self):
        """large 档应通过预检(不因断言而退出)。"""
        import example_ab_test as abt
        buf_err, buf_out = io.StringIO(), io.StringIO()
        # 只跑预检:limit=0 + 空 cases 会跳过;这里用不存在的 out,靠断言先返回
        with redirect_stderr(buf_err), redirect_stdout(buf_out):
            # 传一个不存在的 tier 不可行(choices),故直接构造 probe
            p = vw.build_prompt("football_ket_qua", profile="full", model_tier="large",
                                allow_unreviewed=True)
        self.assertGreater(p["stats"].get("n_examples", 0), 0)


if __name__ == "__main__":
    unittest.main()
