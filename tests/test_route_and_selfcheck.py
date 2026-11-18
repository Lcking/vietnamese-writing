"""通用体裁自动路由 + 生成后自检测试。

背景:用户记不住 20 个体裁名。detect_genre 此前只认足球和社交,
其他全部返回 None → 走最小通用规则,等于通用能力形同虚设。
"""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))

import viet_writer as vw  # noqa: E402


ROUTES = [
    ("Viết bài giới thiệu về phở Hà Nội", "am_thuc"),
    ("Viết bài về du lịch Hà Giang mùa lúa chín", "du_lich"),
    ("Phân tích lãi suất tiết kiệm ngân hàng tăng", "tai_chinh"),
    ("Ứng dụng trí tuệ nhân tạo trong giáo dục", "cong_nghe"),
    ("Tầm quan trọng của tiêm chủng định kỳ", "y_te"),
    ("Cải cách hành chính cấp xã", "the_che"),
    ("Chiến thắng Bạch Đằng năm 1288", "lich_su"),
    ("Di sản nhã nhạc cung đình Huế", "di_san"),
    ("Viết truyện ngắn về người bà ở làng quê", "van_hoc"),
    ("Kỹ năng quản lý thời gian cho người đi làm", "cong_viec"),
    ("Viết một bài về 美食 truyền thống", "am_thuc"),
    ("Viết bản tin trận Việt Nam - Thái Lan", "football_tin_tuc"),
]


@pytest.mark.parametrize("task,expected", ROUTES)
def test_route(task, expected):
    assert vw.detect_genre(task) == expected


def test_football_still_wins():
    """足球任务不能被通用路由抢走。"""
    for t in ["Nhận định trận Việt Nam - Thái Lan",
              "Tin chuyển nhượng Chelsea chiêu mộ tiền đạo",
              "Bình luận trận chung kết Champions League"]:
        g = vw.detect_genre(t)
        assert g and g.startswith("football_"), f"{t} → {g}"


def test_no_genre_returns_none_or_valid():
    """完全无关的任务不该硬塞体裁。"""
    g = vw.detect_genre("Xin chào, hôm nay trời đẹp")
    assert g is None or g in vw.GENRES


def test_generic_route_covers_all_20():
    """GENERIC_ROUTE 必须覆盖全部 20 个通用体裁。"""
    covered = {g for g, _ in vw.GENERIC_ROUTE}
    expect = {
        "van_hoc", "van_hoa_phong_tuc", "nghe_thuat", "ton_giao",
        "doi_song", "giai_tri", "am_thuc", "du_lich", "cong_viec",
        "lich_su", "dia_ly", "di_san", "quan_su", "the_che",
        "y_te", "tai_chinh", "cong_nghe", "hoc_thuat", "phap_luat",
        "giao_duc",
    }
    assert expect <= covered, f"未覆盖: {expect - covered}"


def test_write_meta_has_han_check(monkeypatch):
    """write() 必须在 meta 里报告汉字残留。"""
    class FakeResp:
        text = "Tiêu đề\n\nĐây là nội dung tiếng Việt 布满 chữ Hán."
        finish_reason = "stop"
        truncated = False
        usage = {}

    class FakeClient:
        def chat(self, system, user, **kw):
            return FakeResp()

    text = vw.write(FakeClient(), "Viết bài về phở", genre="am_thuc",
                    profile="full", model_tier="large")
    meta = vw.write.last_meta
    assert meta["han_clean"] is False
    assert "布满" in meta["han_residue"]
    assert "布满" in text   # 不静默删改,只标记


def test_write_clean_text_meta(monkeypatch):
    class FakeResp:
        text = "Phở Hà Nội\n\nNước dùng là linh hồn của bát phở."
        finish_reason = "stop"
        truncated = False
        usage = {}

    class FakeClient:
        def chat(self, system, user, **kw):
            return FakeResp()

    vw.write(FakeClient(), "Viết bài về phở", genre="am_thuc",
             profile="full", model_tier="large")
    assert vw.write.last_meta["han_clean"] is True


def test_normalize_strips_title_bold():
    """生成后应立即去掉首行标题的 markdown 包裹。"""
    class FakeResp:
        text = "**Phở Hà Nội: linh hồn ẩm thực**\n\nNội dung bài viết."
        finish_reason = "stop"
        truncated = False
        usage = {}

    class FakeClient:
        def chat(self, system, user, **kw):
            return FakeResp()

    out = vw.write(FakeClient(), "Viết bài về phở", genre="am_thuc",
                   profile="full", model_tier="large")
    assert not out.startswith("**")
    assert out.startswith("Phở Hà Nội")
