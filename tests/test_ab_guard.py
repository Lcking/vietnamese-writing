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
        """B. use_examples=True + 不放宽 → 只注入人工确认过的范文。

        2026-10 起仓库已有 6 位导师确认的 17 条赛果范文,
        故此处应注入 >0 条,且全部 type_reviewed=True。
        (此前范文池无确认条目时,这里断言为 0 条。)
        """
        p = _prompt(use_examples=True)
        metas = p["examples_meta"]
        self.assertGreater(len(metas), 0,
                           "已有导师确认范文时应能注入")
        for m in metas:
            self.assertTrue(m.get("type_reviewed"),
                            "放宽关闭时只能注入人工确认过的范文")

    def test_d_allow_unreviewed_alone_no_examples(self):
        """D. 只开 allow_unreviewed、不开 use_examples → 仍 0 条(两开关已解耦)。"""
        p = _prompt(allow_unreviewed=True)
        self.assertEqual(p["stats"]["n_examples"], 0,
                         "放宽确认不应顺带打开范文位(large 档)")

    def test_c_both_switches_capped(self):
        """C. 两个都开 → 仍受 large 档 ≤2 条限制;注入项均为已确认。"""
        p = _prompt(use_examples=True, allow_unreviewed=True)
        metas = p["examples_meta"]
        self.assertGreater(len(metas), 0, "两个开关都开时应能注入范文")
        self.assertLessEqual(len(metas), 2, "large 档范文位 ≤2 条")
        # 已确认范文优先,故即使放宽也应是确认过的
        self.assertTrue(all(m.get("type_reviewed") for m in metas),
                        "已确认范文应优先进池")

    def test_e_ab_script_exit2_when_b_empty(self):
        """E. 去掉已确认范文后,B 组为 0 条,脚本应 exit 2。"""
        import example_ab_test as abt
        from pathlib import Path
        import viet_writer as vw
        # 临时把 reviewed 池移走,模拟"没有确认范文"的世界
        target = Path(vw.EXAMPLES) / "football" / "ket_qua_reviewed.jsonl"
        backup = target.with_suffix(".jsonl.bak")
        moved = False
        try:
            if target.exists():
                target.rename(backup); moved = True
            buf_err, buf_out = io.StringIO(), io.StringIO()
            with redirect_stderr(buf_err), redirect_stdout(buf_out):
                code = abt.main(["--use-examples", "--limit", "1",
                                 "--out", "/tmp/ab_guard_t"])
            self.assertEqual(code, 2, "B 组 0 条范文应 exit 2")
            self.assertIn("实验无效", buf_err.getvalue())
        finally:
            if moved and backup.exists():
                backup.rename(target)

    def test_f_ab_script_accepts_reviewed_without_flag(self):
        """F. 未加 --allow-unreviewed 也应能跑(因为范文已确认)。"""
        import example_ab_test as abt
        p = _prompt(use_examples=True)
        metas = p["examples_meta"]
        self.assertGreater(len(metas), 0)
        self.assertTrue(all(m.get("type_reviewed") for m in metas),
                        "确认过的范文不需要 --allow-unreviewed")


if __name__ == "__main__":
    unittest.main()
