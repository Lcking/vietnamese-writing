#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_regression_check.py — 冒烟测试。

确保 bin/regression_check.py 的主函数能跑完、通过数 > 0。
(此前它因缺少 _load_task 定义而崩溃,却没有测试覆盖到主函数。)
"""
import io
import subprocess
import sys
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))


class TestRegressionCheckSmoke(unittest.TestCase):

    def test_main_runs_and_passes(self):
        """直接调用 main():应跑完、通过数 > 0、无失败。"""
        import regression_check as rc
        buf = io.StringIO()
        with redirect_stdout(buf):
            code = rc.main()
        out = buf.getvalue()
        self.assertEqual(code, 0, f"main() 返回 {code};输出:\n{out}")
        self.assertIn("通过", out)
        # 解析"结果: P/T 通过"里的 P 和 T
        import re
        m = re.search(r"结果:\s*(\d+)/(\d+)\s*通过", out)
        self.assertIsNotNone(m, f"未找到结果行:\n{out}")
        passed, total = int(m.group(1)), int(m.group(2))
        self.assertGreater(total, 0, "回归表不应为空(稿件已放进仓库)")
        self.assertEqual(total, passed, f"有失败项:\n{out}")

    def test_load_task_defined(self):
        """_load_task 必须存在且能按文件名反查任务文本。"""
        import regression_check as rc
        self.assertTrue(callable(getattr(rc, "_load_task", None)))
        task = rc._load_task("M1_hai_phong_thanh_hoa")
        self.assertIsNotNone(task)
        self.assertIn("Hải Phòng", task)

    def test_real_dir_points_to_verified_matches(self):
        """REAL 必须指向 real_matches_20261013(不是占位目录)。"""
        import regression_check as rc
        self.assertEqual(rc.REAL.name, "real_matches_20261013")

    def test_cli_runs(self):
        """命令行方式也应正常退出。"""
        r = subprocess.run([sys.executable, str(ROOT / "bin/regression_check.py")],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, f"stderr:\n{r.stderr}")
        self.assertIn("通过", r.stdout)


if __name__ == "__main__":
    unittest.main()
