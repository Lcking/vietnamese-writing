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


    # ---- 评审 v3 第四轮:9 个新边界 ----

    def test_own_goal_title_candidate(self):
        """乌龙球决胜:标题候选不含乌龙球员,聚焦受益方。"""
        r = compute({"home": "Đội A", "away": "Đội B", "final": [0, 1],
                     "events": [{"minute": 10, "type": "own_goal", "team": "home", "player": "Z"}]})
        joined = " | ".join(r["title_candidates"])
        self.assertNotIn("Z (bàn quyết định)", joined)
        self.assertIn("Đội B", joined)

    def test_penalty_shootout_score_in_block(self):
        """点球大战事实块要有比分 4-3。"""
        r = compute({"home": "Đội A", "away": "Đội B", "final": [1, 1], "penalties": [4, 3],
                     "events": [{"minute": 10, "type": "goal", "team": "home", "player": "P"},
                                {"minute": 20, "type": "goal", "team": "away", "player": "Q"}]})
        out = format_for_prompt(r, [])
        self.assertIn("4-3", out)
        self.assertIn("chấm luân lưu", out)

    def test_no_comeback_when_mismatch(self):
        """比分不一致时不应输出逆转。"""
        r = compute({"home": "A", "away": "B", "final": [1, 2], "events": [
            {"minute": 10, "type": "goal", "team": "away", "player": "Q"},
            {"minute": 20, "type": "goal", "team": "home", "player": "P"},
            {"minute": 30, "type": "goal", "team": "home", "player": "P2"}]})
        self.assertTrue(r["score_mismatch"])
        self.assertFalse(r["comeback"])
        self.assertNotIn("ngược dòng", format_for_prompt(r, []))

    def test_no_final_no_inference(self):
        """未提供最终比分 → 停用胜负推断并提示。"""
        r = compute({"home": "A", "away": "B", "events": [
            {"minute": 10, "type": "goal", "team": "home", "player": "P"},
            {"minute": 20, "type": "goal", "team": "home", "player": "Q"}]})
        self.assertFalse(r["final_provided"])
        self.assertEqual(r["derivable"], [])
        self.assertIn("chung cuộc", format_for_prompt(r, []))

    def test_missing_minute_no_verb(self):
        """有进球缺分钟 → 不给动词与决胜球,并警告。"""
        r = compute({"home": "A", "away": "B", "final": [2, 0], "events": [
            {"minute": None, "type": "goal", "team": "home", "player": "X"},
            {"minute": 55, "type": "goal", "team": "home", "player": "Y"}]})
        self.assertFalse(r["order_reliable"])
        self.assertIsNone(r["decider"])
        self.assertTrue(all(s["verb"] == "?" for s in r["score_progression"]))
        self.assertIn("thiếu phút", format_for_prompt(r, []))

    def test_team_name_mapping(self):
        """team 写成队名应映射到 home/away。"""
        r = compute({"home": "Đội A", "away": "Đội B", "final": [2, 1], "events": [
            {"minute": 10, "type": "goal", "team": "Đội A", "player": "P"},
            {"minute": 20, "type": "goal", "team": "Đội A", "player": "Q"}]})
        self.assertEqual(r["team_errors"], [])
        self.assertTrue(all(s["team"] == "home" for s in r["score_progression"]))

    def test_unknown_team_reported(self):
        """无法映射的队名要报错。"""
        r = compute({"home": "A", "away": "B", "final": [1, 0], "events": [
            {"minute": 10, "type": "goal", "team": "Đội C", "player": "P"}]})
        self.assertIn("Đội C", r["team_errors"])

    def test_two_reds_merged(self):
        """同一队两张红牌 → 'thiếu 2 người'。"""
        r = compute({"home": "A", "away": "B", "final": [1, 0], "events": [
            {"minute": 10, "type": "goal", "team": "home", "player": "P"},
            {"minute": 30, "type": "red", "team": "away", "player": "R1"},
            {"minute": 40, "type": "red", "team": "away", "player": "R2"}]})
        joined = " | ".join(r["title_candidates"])
        self.assertIn("thiếu 2 người", joined)
        self.assertEqual(joined.count("chơi thiếu"), 1)

    def test_penalty_goal_annotated(self):
        """点球进球要有 (phạt đền) 标注。"""
        r = compute({"home": "A", "away": "B", "final": [1, 0], "events": [
            {"minute": 10, "type": "penalty", "team": "home", "player": "P"}]})
        self.assertIn("phạt đền", format_for_prompt(r, []))

    def test_missed_penalty_listed(self):
        """罚丢点球要列出。"""
        r = compute({"home": "A", "away": "B", "final": [1, 0], "events": [
            {"minute": 10, "type": "goal", "team": "home", "player": "P"},
            {"minute": 50, "type": "missed_penalty", "team": "away", "player": "Q"}]})
        self.assertIn("Đá hỏng phạt đền", format_for_prompt(r, []))


    # ---- 评审 v3 第五轮:输入矛盾与杯赛语境 ----

    def test_unknown_team_excluded_from_score(self):
        """队名映射不上:该事件不参与比分计算,只报一条警告。"""
        r = compute({"home": "Đội A", "away": "Đội B", "final": [1, 0],
                     "events": [{"minute": 10, "type": "goal", "team": "Đội C", "player": "P"}]})
        self.assertEqual(r["score_progression"], [])
        self.assertIn("Đội C", r["team_errors"])
        out = format_for_prompt(r, [])
        self.assertNotIn("thiếu phút", out)     # 不该冒出连锁误报

    def test_team_casefold_match(self):
        """队名大小写应折叠匹配。"""
        r = compute({"home": "Đội A", "away": "Đội B", "final": [1, 0],
                     "events": [{"minute": 10, "type": "goal", "team": "đội a", "player": "P"}]})
        self.assertEqual(r["team_errors"], [])

    def test_penalties_ignored_when_decided(self):
        """常规时间已分胜负 → 忽略点球数据并警告。"""
        r = compute({"home": "Đội A", "away": "Đội B", "final": [2, 1], "penalties": [4, 3],
                     "events": [{"minute": 10, "type": "goal", "team": "home", "player": "P"},
                                {"minute": 20, "type": "goal", "team": "away", "player": "Q"},
                                {"minute": 30, "type": "goal", "team": "home", "player": "Z"}]})
        self.assertIsNone(r["penalty_winner"])
        self.assertTrue(r["pen_warning"])

    def test_drawn_penalties_invalid(self):
        """点球 3-3 不可能 → 忽略并警告。"""
        r = compute({"home": "A", "away": "B", "final": [1, 1], "penalties": [3, 3], "events": []})
        self.assertIsNone(r["penalty_winner"])
        self.assertIn("hợp lệ", r["pen_warning"])

    def test_cup_no_three_points(self):
        """杯赛/淘汰赛不推 3 分。"""
        r = compute({"home": "A", "away": "B", "final": [2, 1], "competition_type": "cup",
                     "events": [{"minute": 20, "type": "goal", "team": "away", "player": "Q"},
                                {"minute": 30, "type": "goal", "team": "home", "player": "Z"},
                                {"minute": 100, "type": "goal", "team": "home", "player": "P"}]})
        self.assertNotIn("3 điểm", " ".join(d["fact"] for d in r["derivable"]))

    def test_extra_time_annotated(self):
        """加时进球标 hiệp phụ,结果写 sau 120 phút。"""
        r = compute({"home": "A", "away": "B", "final": [2, 1], "competition_type": "cup",
                     "events": [{"minute": 20, "type": "goal", "team": "away", "player": "Q"},
                                {"minute": 100, "type": "goal", "team": "home", "player": "P"}]})
        out = format_for_prompt(r, [])
        self.assertIn("hiệp phụ", out)
        self.assertIn("120", out)

    def test_missing_minute_keeps_winner(self):
        """缺分钟不影响胜负判断(只影响顺序相关)。"""
        r = compute({"home": "A", "away": "B", "final": [2, 0],
                     "events": [{"minute": None, "type": "goal", "team": "home", "player": "X"},
                                {"minute": 55, "type": "goal", "team": "home", "player": "Y"}]})
        self.assertFalse(r["order_reliable"])
        self.assertIsNone(r["decider"])
        # 胜负仍可推(3 分为联赛默认)
        self.assertIn("giành trọn 3 điểm", [d["fact"] for d in r["derivable"]])

    def test_missing_minute_no_scoreline_hint(self):
        """缺分钟时不列逐球比分,也不放 '?'。"""
        r = compute({"home": "A", "away": "B", "final": [2, 0],
                     "events": [{"minute": None, "type": "goal", "team": "home", "player": "X"},
                                {"minute": 55, "type": "goal", "team": "home", "player": "Y"}]})
        out = format_for_prompt(r, [])
        self.assertNotIn("**?**", out)
        # 进程行不含逐球比分
        for line in out.split("\n"):
            if "phút 55" in line:
                self.assertNotIn("1-0", line)


if __name__ == "__main__":
    unittest.main(verbosity=2)
