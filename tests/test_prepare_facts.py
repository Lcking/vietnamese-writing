#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_prepare_facts.py — 事实预处理测试。

运行: python -m pytest tests/ -q   或   python tests/test_prepare_facts.py
基线样本: eval/regression/the_cong_ha_tinh_20261008/facts.json
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
from prepare_facts import compute, check_input_text  # noqa: E402


def verbs(result):
    return [s["verb"] for s in result["score_progression"]]


def scores(result):
    return [s["score"] for s in result["score_progression"]]


class TestPrepareFacts(unittest.TestCase):
    def load_regression(self):
        f = ROOT / "eval/regression/the_cong_ha_tinh_20261008/facts.json"
        return json.loads(f.read_text(encoding="utf-8"))

    # 回归样本
    def test_regression_verbs(self):
        r = compute(self.load_regression())
        # 与编辑参考改写对齐: 1-2→1-3 用 "nâng tỷ số"
        self.assertEqual(verbs(r), ["mở tỷ số", "gỡ hòa", "vượt lên dẫn", "nâng tỷ số"])
        self.assertEqual(scores(r), ["0-1", "1-1", "1-2", "1-3"])

    def test_regression_decider(self):
        r = compute(self.load_regression())
        self.assertEqual(r["decider"]["minute"], 60)
        self.assertEqual(r["decider"]["player"], "Daniel Passira")

    def test_regression_absent(self):
        r = compute(self.load_regression())
        self.assertIn("round", r["absent"])
        self.assertIn("venue", r["absent"])
        self.assertIn("second_yellow_minute", r["absent"])

    def test_regression_derivable(self):
        r = compute(self.load_regression())
        facts = [d["fact"] for d in r["derivable"]]
        self.assertIn("giành trọn 3 điểm", facts)
        self.assertTrue(any("hiệp một" in f for f in facts))

    def test_regression_double(self):
        r = compute(self.load_regression())
        self.assertTrue(any("cú đúp" in c for c in r["title_candidates"]))

    # 逆转:0-1 落后 → 2-1 反超(胜方曾落后)
    def test_comeback(self):
        r = compute({
            "home": "A", "away": "B", "final": [2, 1],
            "events": [
                {"minute": 10, "type": "goal", "team": "away", "player": "X"},
                {"minute": 50, "type": "goal", "team": "home", "player": "Y"},
                {"minute": 80, "type": "goal", "team": "home", "player": "Z"},
            ]})
        self.assertEqual(verbs(r), ["mở tỷ số", "gỡ hòa", "vượt lên dẫn"])
        self.assertTrue(r["comeback"])
        self.assertEqual(r["decider"]["minute"], 80)

    # 乌龙球:记入受益方
    def test_own_goal(self):
        r = compute({
            "home": "A", "away": "B", "final": [1, 0],
            "events": [
                {"minute": 20, "type": "own_goal", "team": "away", "player": "X"},
            ]})
        self.assertEqual(r["score_progression"][0]["team"], "home")
        self.assertIn("phản lưới nhà", r["score_progression"][0]["verb"])

    # 点球:算普通进球
    def test_penalty(self):
        r = compute({
            "home": "A", "away": "B", "final": [1, 0],
            "events": [{"minute": 30, "type": "penalty", "team": "home", "player": "Y"}],
        })
        self.assertEqual(r["score_progression"][0]["verb"], "mở tỷ số")

    # 平局:无决胜事件
    def test_draw_no_decider(self):
        r = compute({
            "home": "A", "away": "B", "final": [2, 2],
            "events": [
                {"minute": 10, "type": "goal", "team": "home", "player": "X"},
                {"minute": 30, "type": "goal", "team": "away", "player": "Y"},
                {"minute": 60, "type": "goal", "team": "home", "player": "Z"},
                {"minute": 90, "type": "goal", "team": "away", "player": "W"},
            ]})
        self.assertIsNone(r["decider"])

    # 大胜 5-0:nhân đôi cách biệt 只在 1→2 时
    def test_blowout(self):
        r = compute({
            "home": "A", "away": "B", "final": [5, 0],
            "events": [{"minute": 10 * i, "type": "goal", "team": "home", "player": f"P{i}"}
                       for i in range(1, 6)],
        })
        v = verbs(r)
        self.assertEqual(v[0], "mở tỷ số")
        self.assertEqual(v.count("nâng tỷ số"), 4)  # 1-0→2-0 起全部 nâng tỷ số(与参考改写对齐)

    # 输入纠错:1-1 后写 nâng tỷ số
    def test_input_warning_verb(self):
        r = compute(self.load_regression())
        # 输入把 1-1 后的反超写成 "nâng tỷ số ... 2-1"(矛盾:2-1 双方视角都有平局,应用 vượt lên dẫn)
        warns = check_input_text("Passira nâng tỷ số lên 2-1.", r)
        self.assertTrue(any(w["kind"] == "verb_conflict" for w in warns),
                        f"未检测到动词矛盾, warns={warns}")

    # 输入纠错:vòng mới nhất
    def test_input_warning_vague(self):
        r = compute(self.load_regression())
        warns = check_input_text("Trận đấu thuộc vòng mới nhất của V-League.", r)
        self.assertTrue(any(w["kind"] == "vague" for w in warns))


if __name__ == "__main__":
    unittest.main(verbosity=2)
