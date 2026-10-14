#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""tests/test_extract_football.py — 抽取规则单元测试。

覆盖评审要求:
  问题二:办公室省电/女排 3-1/五人制足球 2-1 判为**否**;真 V.League 赛果判为**是**
  问题三:改动 1%/2%/4% 词、真实相似度 ≥0.8 的稿件对,判重率 ≥90%
"""
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

import extract_football as ef  # noqa: E402


class TestKetQuaRule(unittest.TestCase):
    """问题二:赛果判定收紧。"""

    def test_office_tips_not_ket_qua(self):
        t = ("Giải pháp tiết kiệm điện văn phòng. Đội ngũ nhân viên làm việc "
             "1-2 giờ, nghỉ phút 5. Hiệp hội doanh nghiệp khuyến nghị.")
        self.assertFalse(ef.is_ket_qua(t), "办公室省电文不应判为赛果")

    def test_volleyball_not_ket_qua(self):
        t = ("Bóng chuyền nữ Việt Nam thắng Thái Lan 3-1 ở trận đấu vòng bảng, "
             "hiệp 4 gay cấn, phút thi đấu kéo dài.")
        self.assertFalse(ef.is_ket_qua(t), "排球不应判为足球赛果")

    def test_futsal_not_ket_qua(self):
        t = ("Futsal Việt Nam giành chiến thắng 2-1 trước đối thủ ở trận đấu "
             "giao hữu, bàn thắng ở phút 30.")
        self.assertFalse(ef.is_ket_qua(t), "五人制足球暂不收录")

    def test_real_vleague_is_ket_qua(self):
        t = ("Trận đấu giữa Hà Nội và Thanh Hóa tại vòng 3 V.League kết thúc "
             "với tỷ số 2-1. Phút 34, Văn Quyết mở tỷ số cho đội chủ nhà. "
             "Phút 78, đội khách gỡ hòa. Bàn thắng quyết định ở phút 90.")
        self.assertTrue(ef.is_ket_qua(t), "真实 V.League 赛果应判为是")

    def test_scoring_regex_rejects_dates_and_units(self):
        # 用 wash-then-match 的真实接口 find_scores(先挖日期/量词)
        self.assertFalse(ef.find_scores("ngày 07-25 năm 2023"))
        self.assertFalse(ef.find_scores("1-2 thìa cà phê"))
        self.assertFalse(ef.find_scores("5-10 kg"))
        self.assertFalse(ef.find_scores("ngày 12/07/2025"))
        self.assertTrue(ef.find_scores("tỷ số 2-1"))
        self.assertTrue(ef.find_scores("thắng 3-1."))

    def test_common_words_not_context(self):
        """普通词(giải/đội/hiệp)不应算作比赛语境。"""
        t = "Giải pháp cho đội ngũ, hiệp hội đề xuất. Tỷ số 2-1."
        self.assertLess(ef.ctx_hits(t), 2,
                        "giải pháp/đội ngũ/hiệp hội 不应贡献语境词")


class TestLshDedup(unittest.TestCase):
    """问题三:分段 LSH 判重率 ≥90%(真实相似度 ≥0.8)。"""

    @staticmethod
    def _mk_text(n_words, seed):
        import random
        rnd = random.Random(seed)
        return " ".join(f"w{rnd.randint(0, 999)}" for _ in range(n_words))

    @staticmethod
    def _jaccard(a, b):
        import re
        ta = set(re.findall(r"\w+", a))
        tb = set(re.findall(r"\w+", b))
        return len(ta & tb) / len(ta | tb)

    def _dup_rate(self, pct):
        """改动 pct 比例的词,统计被判重的比例。"""
        import random
        hits = 0
        N = 100
        for s in range(N):
            rnd = random.Random(s)
            base = [f"w{rnd.randint(0, 499)}" for _ in range(400)]
            mod = list(base)
            k = max(1, int(len(base) * pct))
            for i in rnd.sample(range(len(base)), k):
                mod[i] = f"x{rnd.randint(1000, 9999)}"
            a, b = " ".join(base), " ".join(mod)
            sim = self._jaccard(a, b)
            if sim < 0.8:
                continue
            sa = ef.minhash_sig(a.split())
            sb = ef.minhash_sig(b.split())
            ba, bb = set(ef.lsh_bands(sa)), set(ef.lsh_bands(sb))
            if ba & bb:
                hits += 1
        return hits

    def test_dup_rate_1pct(self):
        self.assertGreaterEqual(self._dup_rate(0.01), 90,
                                "改动 1% 词的近似重复应 ≥90% 判重")

    def test_dup_rate_2pct(self):
        self.assertGreaterEqual(self._dup_rate(0.02), 90,
                                "改动 2% 词的近似重复应 ≥90% 判重")

    def test_dup_rate_4pct(self):
        self.assertGreaterEqual(self._dup_rate(0.04), 90,
                                "改动 4% 词的近似重复应 ≥90% 判重")


if __name__ == "__main__":
    unittest.main()
