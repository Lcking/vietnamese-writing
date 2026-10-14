#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""赛果判定的单元测试（复审要求，2026-10）。

覆盖：
  1) 7 种标准越南语赛果写法必须能认出比分（含 thắng...trước/trên/trong、giờ nghỉ、phút 90）
  2) 4 个反例仍不能认作比分（量词/日期）
  3) 博彩稿只进 betting 类
运行： python3 -m pytest tests/test_score_parsing.py -q
"""
import importlib.util
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("extract_football", ROOT / "bin" / "extract_football.py")
ef = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ef)


# ---- 正向：必须能认出比分 ----
POSITIVE = [
    "Việt Nam thắng 2-0 trước Thái Lan",
    "Hà Nội thắng 3-1 trên sân nhà",
    "Arsenal thắng 2-1 trong trận đấu",
    "dẫn 1-0 giờ nghỉ",
    "1-0 phút 90",
    "kết thúc với tỷ số 1-1",
    "MU thua 0-3 tại Old Trafford",
]

# ---- 反向：不能被当作比分 ----
NEGATIVE = [
    "1-2 thìa",
    "5-10 kg",
    "1-2 triệu",
    "07-25",
]


def test_positive_score_detection():
    bad = [t for t in POSITIVE if not ef.find_scores(t)]
    assert not bad, f"这些标准赛果写法没认出比分: {bad}"


def test_negative_not_score():
    bad = [t for t in NEGATIVE if ef.find_scores(t)]
    assert not bad, f"这些被误判成比分: {bad}"


def test_betting_only_betting_tag():
    """博彩稿只打 betting 标签，不混入 ket_qua 等。"""
    t = "Soi kèo Arsenal vs Chelsea: nhà cái dự đoán tỷ số 2-1, link vào W88"
    tags = ef.classify(t)
    assert tags == ["betting"], f"博彩稿标签错误: {tags}"


def test_ket_qua_score_ordering():
    """真赛果稿的排序分应高于顺带提到比分的一般稿。"""
    real = ("Hà Nội FC thắng 2-0 trên sân vận động Hàng Đẫy. "
            "Phút 23, Văn Quyết mở tỷ số. Phút 67, Văn Toàn nâng tỷ số lên 2-0.")
    weak = "Đội bóng hôm nay có tỷ số 1-0 nhưng bài này nói về lịch thi đấu."
    assert ef.ket_qua_score(real) > ef.ket_qua_score(weak), \
        f"排序分没区分开: real={ef.ket_qua_score(real)} weak={ef.ket_qua_score(weak)}"


if __name__ == "__main__":
    fails = 0
    for fn in [test_positive_score_detection, test_negative_not_score,
               test_betting_only_betting_tag, test_ket_qua_score_ordering]:
        try:
            fn()
            print(f"  ✓ {fn.__name__}")
        except AssertionError as e:
            fails += 1
            print(f"  ✗ {fn.__name__}: {e}")
    print(f"\n{'全部通过' if not fails else str(fails)+' 项失败'}")
    sys.exit(1 if fails else 0)
