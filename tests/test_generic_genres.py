"""通用体裁接入测试:20 个子体裁必须同时有规则卡和范文池。

背景:20 个通用子体裁(am_thuc/tai_chinh/y_te/...)的蒸馏范文曾长期
躺在本地 distill_work/,从未进入 skill——GENRES 里没有它们、CARD_MAP
没有映射、examples/generic/ 目录不存在。本轮补齐后锁住,防止回归。

不校验范文内容质量(那靠人工确认),只校验"能被注入"这一事实。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))

import viet_writer as vw  # noqa: E402

GENERIC_20 = [
    "van_hoc", "van_hoa_phong_tuc", "nghe_thuat", "ton_giao",
    "doi_song", "giai_tri", "am_thuc", "du_lich", "cong_viec",
    "lich_su", "dia_ly", "di_san", "quan_su", "the_che",
    "y_te", "tai_chinh", "cong_nghe", "hoc_thuat", "phap_luat",
    "giao_duc",
]


@pytest.mark.parametrize("genre", GENERIC_20)
def test_genre_registered(genre):
    """20 个体裁都必须在 GENRES 和 GENERIC_MAP 里。"""
    assert genre in vw.GENRES, f"{genre} 不在 GENRES"
    assert genre in vw.GENERIC_MAP, f"{genre} 不在 GENERIC_MAP"
    assert genre in vw.CARD_MAP, f"{genre} 不在 CARD_MAP"


@pytest.mark.parametrize("genre", GENERIC_20)
def test_card_exists(genre):
    """每个体裁都要有规则卡文件,且不含汉字、不超长。"""
    p = vw.CARDS / vw.CARD_MAP[genre]
    assert p.exists(), f"{genre} 缺规则卡 {p.name}"
    txt = p.read_text(encoding="utf-8")
    assert len(txt) < 1700, f"{p.name} 超长 {len(txt)}"
    import re
    assert not re.search(r"[\u4e00-\u9fff]", txt), f"{p.name} 含汉字"


@pytest.mark.parametrize("genre", GENERIC_20)
def test_examples_injectable(genre):
    """每个体裁都必须能注入范文(种子或全量池至少其一存在)。"""
    fname = vw.GENERIC_MAP[genre]
    base = vw.EXAMPLES / "generic"
    seed = base / fname.replace(".jsonl", "_seed.jsonl")
    full = base / fname
    assert seed.exists() or full.exists(), f"{genre}: 范文池缺失({seed.name}/{full.name})"

    r = vw.build_prompt(genre, profile="full", model_tier="large",
                        use_examples=True, allow_unreviewed=True)
    assert r["stats"]["n_examples"] > 0, f"{genre} 注入范文数 0"
    assert r["stats"]["genre_chars"] > 0, f"{genre} 规则卡字符数 0"


def test_dropped_genre_name_validated():
    """不存在的体裁应被拒绝(防止拼错静默生效)。"""
    with pytest.raises(Exception):
        vw.build_prompt("khong_ton_tai", profile="full")
