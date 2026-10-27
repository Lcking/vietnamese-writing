#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_editor_edits.py — 母语导师改稿的回归测试。

数据来源: eval/editor_edits/football_ket_qua_2026_10.jsonl
  6 位越南语导师盲评 10/2026 时写下的「原句 → 改后」对(13 条有效)。
  这是目前唯一的母语金标准数据。

每个断言检查: 导师改后的写法,是否符合规则卡/检查器的立场。
不是检查"模型必须写这句",而是"导师认为对的写法不应被判错"。
"""
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

EDITS = ROOT / "eval" / "editor_edits" / "football_ket_qua_2026_10.jsonl"


def load_edits():
    if not EDITS.exists():
        return []
    return [json.loads(l) for l in EDITS.read_text(encoding="utf-8").splitlines()
            if l.strip()]


class TestEditorEditsDataset(unittest.TestCase):
    """数据集本身的结构校验。"""

    def test_dataset_exists_and_nonempty(self):
        edits = load_edits()
        self.assertGreater(len(edits), 0, "母语改稿数据集为空")

    def test_all_have_required_fields(self):
        for e in load_edits():
            for k in ("id", "draft", "edited", "review_status"):
                self.assertIn(k, e, f"{e.get('id')} 缺字段 {k}")
            self.assertEqual(e["review_status"], "native_confirmed",
                             f"{e['id']} 未经母语确认")

    def test_draft_differs_from_edited(self):
        for e in load_edits():
            self.assertNotEqual(e["draft"].strip(), e["edited"].strip(),
                                f"{e['id']} 原句与改句相同")


class TestEditorPreferredForms(unittest.TestCase):
    """导师改后采用的写法,规则卡必须支持。"""

    def test_quan_binh_ty_so_accepted(self):
        """导师用『quân bình tỉ số』替代『gỡ hòa』(B14)。"""
        edits = load_edits()
        hit = [e for e in edits if "quân bình" in e["edited"].lower()]
        self.assertTrue(hit, "数据集中应有 quân bình tỉ số 的改稿")
        # 规则卡应已收录
        card = (ROOT / "references/cards/ket_qua_tran.md").read_text(encoding="utf-8")
        self.assertIn("quân bình", card.lower(),
                      "规则卡未收录导师认可的 quân bình tỉ số")

    def test_loi_nguoc_dong_accepted(self):
        """导师用『lội ngược dòng』(B14)。"""
        card = (ROOT / "references/cards/ket_qua_tran.md").read_text(encoding="utf-8")
        self.assertIn("lội ngược dòng", card)

    def test_vuon_len_dan_truoc_accepted(self):
        """导师把『đưa X dẫn 3-2』改成『giúp X vươn lên dẫn trước 3-2』(B13)。"""
        card = (ROOT / "references/cards/ket_qua_tran.md").read_text(encoding="utf-8")
        self.assertIn("vươn lên dẫn trước", card)

    def test_don_tiep_required(self):
        """导师把『X tiếp Y』改成『X đón tiếp』(B01)。"""
        card = (ROOT / "references/cards/ket_qua_tran.md").read_text(encoding="utf-8")
        self.assertIn("đón tiếp", card)

    def test_ban_thang_quyet_dinh_for_last_goal(self):
        """导师要求制胜球写『bàn thắng quyết định』/『ấn định thắng lợi』(B13)。"""
        card = (ROOT / "references/cards/ket_qua_tran.md").read_text(encoding="utf-8")
        self.assertIn("bàn thắng quyết định", card)
        self.assertIn("ấn định thắng lợi", card)

    def test_lam_chu_the_tran_not_doan_dau(self):
        """导师把『làm chủ thế đoạn đầu』改成『làm chủ thế trận』(B11)。"""
        card = (ROOT / "references/cards/ket_qua_tran.md").read_text(encoding="utf-8")
        self.assertIn("làm chủ thế trận", card)
        # 错误表里应明确列出对错
        self.assertIn("làm chủ thế đoạn đầu", card)

    def test_relative_time_variation(self):
        """导师要求变化时间表达(9 phút sau / phút thi đấu thứ N)(B14, B17)。"""
        card = (ROOT / "references/cards/ket_qua_tran.md").read_text(encoding="utf-8")
        self.assertIn("phút sau", card)
        self.assertIn("phút thi đấu thứ", card)

    def test_var_order_documented(self):
        """导师要求 VAR 顺序:进球→复核→认定(B12)。"""
        card = (ROOT / "references/cards/ket_qua_tran.md").read_text(encoding="utf-8")
        self.assertIn("VAR", card)


class TestS21Downgraded(unittest.TestCase):
    """导师盲审结论: 独立比分行不该阻断发布(B01 两位导师判'可直接发')。"""

    def test_s21_is_non_blocking(self):
        import check_style as cs
        text = "Hải Phòng 1-2 Thanh Hóa.\n\nPhút 15, Matheus Martins mở tỷ số."
        facts = {"home": "Hải Phòng", "away": "Thanh Hóa"}
        issues = cs.check(text, facts=facts, task="Viết bản tin kết quả.")
        s21 = [i for i in issues if i["rule"] == "S21"]
        self.assertTrue(s21, "应检出独立比分行")
        for i in s21:
            self.assertFalse(i["blocking"], "S21 应已降为建议修订(非阻断)")


if __name__ == "__main__":
    unittest.main()
