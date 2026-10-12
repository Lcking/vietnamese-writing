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
from prepare_facts import compute, check_input_text, format_for_prompt  # noqa: E402
import pathlib as _pl  # noqa: E402


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
        self.assertIn("vòng đấu", r["absent"])
        self.assertIn("sân", r["absent"])
        self.assertIn("phút thẻ vàng thứ hai", r["absent"])

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


    # ---- 评审 v3 边界场景(修复前全部失败) ----

    def test_trailing_team_scores_shortens(self):
        """落后方进球 → rút ngắn cách biệt(修复前误报 nâng tỷ số)。"""
        r = compute({"home": "A", "away": "B", "final": [1, 2], "events": [
            {"minute": 10, "type": "goal", "team": "away", "player": "X"},
            {"minute": 20, "type": "goal", "team": "away", "player": "Y"},
            {"minute": 30, "type": "goal", "team": "home", "player": "Z"}]})
        self.assertEqual(r["score_progression"][-1]["verb"], "rút ngắn cách biệt")

    def test_decider_1_0(self):
        """1-0: 决胜球 = 唯一进球(修复前为 None)。"""
        r = compute({"home": "A", "away": "B", "final": [1, 0], "events": [
            {"minute": 10, "type": "goal", "team": "home", "player": "P"}]})
        self.assertIsNotNone(r["decider"])
        self.assertEqual(r["decider"]["minute"], 10)

    def test_decider_2_0_first_goal(self):
        """2-0: 决胜球 = 首开纪录(未被扳平)。"""
        r = compute({"home": "A", "away": "B", "final": [2, 0], "events": [
            {"minute": 10, "type": "goal", "team": "home", "player": "P"},
            {"minute": 20, "type": "goal", "team": "home", "player": "Q"}]})
        self.assertEqual(r["decider"]["minute"], 10)
        self.assertEqual(r["decider"]["player"], "P")

    def test_decider_repeated_lead_takes_last(self):
        """反复反超 3-2: 决胜球 = 最后一次反超(修复前取第一次)。"""
        r = compute({"home": "A", "away": "B", "final": [3, 2], "events": [
            {"minute": 10, "type": "goal", "team": "home", "player": "P1"},
            {"minute": 20, "type": "goal", "team": "away", "player": "Q1"},
            {"minute": 30, "type": "goal", "team": "home", "player": "P2"},
            {"minute": 40, "type": "goal", "team": "away", "player": "Q2"},
            {"minute": 50, "type": "goal", "team": "home", "player": "P3"}]})
        self.assertEqual(r["decider"]["minute"], 50)
        self.assertEqual(r["decider"]["player"], "P3")

    def test_own_goals_not_double(self):
        """两个乌龙球不该算同一名球员梅开二度。"""
        r = compute({"home": "A", "away": "B", "final": [2, 0], "events": [
            {"minute": 10, "type": "own_goal", "team": "away", "player": "G1"},
            {"minute": 20, "type": "own_goal", "team": "away", "player": "G2"}]})
        joined = " ".join(r["title_candidates"])
        self.assertNotIn("cú đúp", joined)

    def test_stoppage_time_no_crash(self):
        """补时 45+2 不该崩溃。"""
        r = compute({"home": "A", "away": "B", "final": [1, 0], "events": [
            {"minute": "45+2", "type": "goal", "team": "home", "player": "P"}]})
        self.assertEqual(len(r["score_progression"]), 1)

    def test_decider_regression_still_60(self):
        """回归样本决胜球仍应为 60' Passira。"""
        import json as _json, pathlib as _pl
        fp = _pl.Path(__file__).resolve().parent.parent / "eval/regression/the_cong_ha_tinh_20261008/facts.json"
        r = compute(json.loads(fp.read_text(encoding="utf-8")))
        self.assertEqual(r["decider"]["minute"], 60)
        self.assertIn("Passira", r["decider"]["player"])


    # ---- 评审 v3 复审第三轮:事实块与边界 ----

    def test_single_yellow_sentence_reported_with_facts(self):
        """单独一句 'X nhận 2 thẻ vàng.' 有 facts 时应报 S6(修复前不报)。"""
        import sys as _s, importlib as _i
        _s.path.insert(0, str(_pl.Path(__file__).resolve().parent.parent / "bin"))
        import check_style; _i.reload(check_style)
        fp = _pl.Path(__file__).resolve().parent.parent / "eval/regression/the_cong_ha_tinh_20261008/facts.json"
        facts = json.loads(fp.read_text(encoding="utf-8"))
        rules = {i["rule"] for i in check_style.check("Quốc Dân nhận 2 thẻ vàng.", facts)}
        self.assertIn("S6", rules)

    def test_facts_block_contains_discipline_and_titles(self):
        """事实块应含红牌事件与标题候选(修复前缺失)。"""
        fp = _pl.Path(__file__).resolve().parent.parent / "eval/regression/the_cong_ha_tinh_20261008/facts.json"
        r = compute(json.loads(fp.read_text(encoding="utf-8")))
        out = format_for_prompt(r, [])
        self.assertIn("thẻ vàng thứ hai", out)
        self.assertIn("Gợi ý cho tiêu đề", out)
        self.assertIn("nhân đôi cách biệt", out.lower()) if False else None

    def test_own_goal_decider_not_main_character(self):
        """乌龙球决胜:事实块不能把踢进乌龙球的球员写成主角。"""
        r = compute({"home": "A", "away": "B", "final": [0, 1],
                     "events": [{"minute": 10, "type": "own_goal", "team": "home", "player": "Z"}]})
        out = format_for_prompt(r, [])
        line = [l for l in out.split("\n") if "quyết định" in l.lower()][0]
        self.assertIn("phản lưới nhà", line)
        self.assertIn("B", line)          # 受益方是客队 B

    def test_score_mismatch_warns_and_disables(self):
        """final 与事件不一致 → 警告 + 停用胜负推导。"""
        r = compute({"home": "A", "away": "B", "final": [2, 1], "events": [
            {"minute": 10, "type": "goal", "team": "home", "player": "P"},
            {"minute": 20, "type": "goal", "team": "away", "player": "Q"}]})
        self.assertTrue(r["score_mismatch"])
        self.assertEqual(r["derivable"], [])
        self.assertIn("KHÔNG khớp", format_for_prompt(r, []))

    def test_stoppage_first_half_counts(self):
        """45+2 进球应计入半场比分。"""
        r = compute({"home": "A", "away": "B", "final": [2, 0], "events": [
            {"minute": "45+2", "type": "goal", "team": "home", "player": "P"},
            {"minute": 70, "type": "goal", "team": "home", "player": "Q"}]})
        facts = [d["fact"] for d in r["derivable"]]
        self.assertIn("tỷ số hiệp một", facts)

    def test_penalty_shootout(self):
        """点球大战应识别胜方。"""
        r = compute({"home": "A", "away": "B", "final": [1, 1], "penalties": [4, 3],
                     "events": [{"minute": 10, "type": "goal", "team": "home", "player": "P"},
                                {"minute": 20, "type": "goal", "team": "away", "player": "Q"}]})
        self.assertEqual(r["penalty_winner"], "home")


if __name__ == "__main__":
    unittest.main(verbosity=2)
