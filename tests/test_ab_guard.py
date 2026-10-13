#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_ab_guard.py — 对照实验的档位与范文准入断言。

背景(评审两轮意见):
  1. large 档原本不注入范文 → A/B 两组提示完全相同,实验会白跑。
  2. 修法一度把"打开范文位"绑在 allow_unreviewed 上,而后者会关掉
     "必须人工确认"筛选 → 注入的是旧池子里误标的稿件。
  修正: use_examples 与 allow_unreviewed 拆成两个互不影响的开关。

覆盖:
  A. large 档范文位默认关闭;use_examples=True 才打开
  B. 打开范文位但没有确认过的范文 → 注入 0 条
  C. 打开范文位且允许未确认 → 只注入(全部)未确认范文时,断言应报错
  D. 只开 allow_unreviewed、不开 use_examples → large 档仍 0 条
  E. 对照脚本在 B 组范文为 0 时 exit 2
"""
import io
import sys
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

import viet_writer as vw  # noqa: E402


def _prompt(**kw):
    base = dict(genre="football_ket_qua", profile="full", model_tier="large")
    base.update(kw)
    return vw.build_prompt(**base)


class TestExampleSlotSwitches(unittest.TestCase):

    def test_a_large_default_off(self):
        """A. 不传开关 → 0 条范文(large 档范文位默认关闭)。"""
        p = _prompt()
        self.assertEqual(p["stats"]["n_examples"], 0)
        self.assertEqual(len(p["examples_meta"]), 0)

    def test_b_use_examples_but_none_reviewed(self):
        """B. use_examples=True + 不放宽 → 只能注入人工确认过的;
        当前仓库没有确认过的赛果范文 → 0 条。"""
        p = _prompt(use_examples=True)
        self.assertEqual(p["stats"]["n_examples"], 0,
                         "没有确认过的范文时应注入 0 条,不能拿未确认的凑数")
        for m in p["examples_meta"]:
            self.assertTrue(m.get("type_reviewed"))

    def test_d_allow_unreviewed_alone_no_examples(self):
        """D. 只开 allow_unreviewed、不开 use_examples → 仍 0 条(两开关已解耦)。"""
        p = _prompt(allow_unreviewed=True)
        self.assertEqual(p["stats"]["n_examples"], 0,
                         "放宽确认不应顺带打开范文位(large 档)")

    def test_c_both_switches_injects_unreviewed(self):
        """C. 两个都开 → 可注入,但注入项均为未确认(type_reviewed=False),
        脚本据此报错。"""
        p = _prompt(use_examples=True, allow_unreviewed=True)
        metas = p["examples_meta"]
        self.assertGreater(len(metas), 0, "两个开关都开时应能注入范文")
        self.assertTrue(all(not m.get("type_reviewed") for m in metas),
                        "当前仓库范文均未人工确认,故应全部 type_reviewed=False")
        self.assertLessEqual(len(metas), 2, "large 档范文位 ≤2 条")

    def test_e_ab_script_exit2_when_b_empty(self):
        """E. 脚本在 B 组范文为 0 时 exit 2,不出报告。"""
        import example_ab_test as abt
        buf_err, buf_out = io.StringIO(), io.StringIO()
        with redirect_stderr(buf_err), redirect_stdout(buf_out):
            code = abt.main(["--use-examples", "--limit", "1", "--out", "/tmp/ab_guard_t"])
        self.assertEqual(code, 2, "B 组 0 条范文应 exit 2")
        self.assertIn("实验无效", buf_err.getvalue())

    def test_f_ab_script_rejects_unreviewed_without_flag(self):
        """E2. 脚本默认拒绝注入未确认范文(需显式 --allow-unreviewed)。"""
        import example_ab_test as abt
        # 直接构造 probe 检验判定逻辑,不真跑模型
        p = _prompt(use_examples=True, allow_unreviewed=True)
        unrev = [m for m in p["examples_meta"] if not m.get("type_reviewed")]
        self.assertTrue(unrev, "当前范文应全为未确认,断言才有意义")
        # 未加 --allow-unreviewed 时应被拒
        buf_err, buf_out = io.StringIO(), io.StringIO()
        with redirect_stderr(buf_err), redirect_stdout(buf_out):
            code = abt.main(["--use-examples", "--limit", "1", "--out", "/tmp/ab_guard_t2"])
        self.assertEqual(code, 2)


if __name__ == "__main__":
    unittest.main()
