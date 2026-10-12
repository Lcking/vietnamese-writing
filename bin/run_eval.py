#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
run_eval.py — Bộ đánh giá độc lập: chạy 3 cấu hình (raw / min / full) trên evalset.

Mục đích: so sánh chất lượng đầu ra giữa:
  - raw : mô hình nền, KHÔNG có skill (system prompt rỗng)
  - min : chỉ quy tắc tối thiểu (1 file global core), không ví dụ
  - full: skill đầy đủ (quy tắc + ví dụ few-shot)

Ghi lại mỗi ca: đầu ra, số ký tự, thời gian, token, finish_reason.
Kèm kiểm tra tự động các "bẫy" (từ cấm, số liệu bịa) — phần chấm điểm tự nhiên
vẫn CẦN người bản ngữ chấm mù (xem eval/README.md).

Dùng:
    VIET_LLM_BASE_URL=... VIET_LLM_API_KEY=... VIET_LLM_MODEL=... \
    python bin/run_eval.py --out eval/results --cases A1,B1,C1
    python bin/run_eval.py --out eval/results          # tất cả ca
"""
import argparse
import re, json, os, sys, time, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "bin"))

# ---- các ca kiểm thử (khớp eval/evalset.md) ----
# G1 结构化事实:直接读回归样本 facts.json(避免手写副本与源文件不一致)
def _load_g1_facts():
    import json as _j, pathlib as _pl
    fp = _pl.Path(__file__).resolve().parent.parent / \
        "eval/regression/the_cong_ha_tinh_20261008/facts.json"
    try:
        return _j.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


CASES = [
    # (id, nhóm, genre, prompt, bẫy cần kiểm tra tự động)
    ("A1", "news", "football_tin_tuc",
     "Viết bản tin: U23 Việt Nam thắng U23 Malaysia 2-0 ở vòng loại, Quang Hải ghi bàn phút 67.",
     {"forbid": [], "expect": ["2-0"]}),
    ("A2", "news", "football_tin_tuc",
     "Viết bản tin: CLB Hà Nội bổ nhiệm HLV mới thay HLV cũ. Không nêu tên cụ thể.",
     {"forbid": [], "expect": []}),
    ("B1", "pre_match", "football_pre_match",
     "Nhận định trước trận Việt Nam — Indonesia tối mai. Không khẳng định chắc chắn kết quả.",
     {"forbid": ["chắc chắn thắng", "sẽ thắng đậm"], "expect": []}),
    ("B2", "pre_match", "football_pre_match",
     "Soi kèo trận Man City — Arsenal. KHÔNG đưa lời khuyên cá cược.",
     {"forbid": ["nên cược", "đặt cược", "cá cược", "kèo thơm", "chắc ăn",
                 "vào tiền", "xuống tiền", "all in", "tỷ lệ ăn tiền"], "expect": []}),
    ("C1", "social", "social_post",
     "Viết bài đăng ngắn: Việt Nam vào chung kết AFF Cup. Không bịa cảnh khán đài.",
     {"forbid": [], "expect": []}),
    ("C2", "social", "social_post",
     "Đăng tin: chưa xác nhận việc HLV từ chức. Phải nêu rõ 'chưa xác nhận'.",
     {"forbid": [], "expect": ["chưa xác nhận", "chưa kiểm chứng", "chưa có thông tin chính thức"]}),
    ("D1", "rewrite", "football_tin_tuc",
     "Viết lại cho tự nhiên (không đổi sự thật): 'Trận đấu đã kết thúc với tỷ số là 2-1 nghiêng về phía đội chủ nhà.'",
     {"forbid": [], "expect": ["2-1"]}),
    ("E1", "low_info", "football_tin_tuc",
     "Viết về một trận bóng đá (không nêu chi tiết gì). KHÔNG bịa đội/tỷ số/thời gian.",
     {"forbid": [], "expect": []}),
    # --- Nhóm F: "thiếu thì bỏ qua" — KHÔNG được viết thành trạng thái khẳng định.
    #     Tiêu chí: số nghi vấn 'trạng thái khẳng định' và 'quan hệ nhân quả' = 0.
    ("F1", "omit_missing", "social_post",
     "Đăng kết quả: Việt Nam thắng 2-0, Quang Hải ghi bàn phút 67. "
     "(Chỉ có vậy — không có thông tin khán giả, không có thông tin vòng sau.)",
     {"forbid": [], "expect": [], "no_fab": ["trạng thái khẳng định (chưa/đang chờ)",
                                              "quan hệ nhân quả"]}),
    ("F2", "omit_missing", "football_tin_tuc",
     "Viết tin ngắn. Dữ kiện: (1) Cầu thủ rời sân ở phút 58. "
     "(2) CLB thông báo cầu thủ bị đau cổ chân phải. Hai dữ kiện riêng biệt.",
     {"forbid": [], "expect": [], "no_fab": ["quan hệ nhân quả"]}),
    # --- Nhóm G: bản tin kết quả (dùng facts.json + check_style) ---
    ("G1", "ket_qua", "football_ket_qua",
     "Viết bản tin kết quả trận Thể Công - Hà Tĩnh (V-League, 8/10/2026). "
     "Dùng đúng dữ kiện: Thể Công 1-3 Hà Tĩnh. Phút 16 Luiz Antonio mở tỷ số. "
     "Phút 33 Khuất Văn Khang gỡ hòa 1-1 (VAR). Phút 60 Daniel Passira nâng lên 2-1. "
     "Phút 64 Passira ghi bàn thứ hai. Quốc Dân nhận thẻ vàng thứ hai.",
     {"forbid": [], "expect": []}, _load_g1_facts()),
    ("G2", "ket_qua", "football_ket_qua",
     "Viết bản tin: đội A thắng đội B 2-1 sau khi bị dẫn 0-1 (ngược dòng). "
     "A ghi bàn ở phút 50 và 80; B mở tỷ số phút 20.",
     {"forbid": [], "expect": []},
     {"home": "A", "away": "B", "final": [2, 1], "events": [
         {"minute": 20, "type": "goal", "team": "away", "player": "B1"},
         {"minute": 50, "type": "goal", "team": "home", "player": "A1"},
         {"minute": 80, "type": "goal", "team": "home", "player": "A2"}]}),
    ("G3", "ket_qua", "football_ket_qua",
     "Viết bản tin: đội A hòa đội B 2-2. A dẫn 2-0 (phút 10, 30), "
     "B gỡ 2-2 (phút 70, 90).",
     {"forbid": [], "expect": []},
     {"home": "A", "away": "B", "final": [2, 2], "events": [
         {"minute": 10, "type": "goal", "team": "home", "player": "A1"},
         {"minute": 30, "type": "goal", "team": "home", "player": "A2"},
         {"minute": 70, "type": "goal", "team": "away", "player": "B1"},
         {"minute": 90, "type": "goal", "team": "away", "player": "B2"}]}),
    ("G4", "ket_qua", "football_ket_qua",
     "Viết bản tin: đội A thắng 1-0 dù chơi thiếu người từ phút 60 "
     "(cầu thủ X nhận thẻ đỏ). Bàn thắng phút 75.",
     {"forbid": [], "expect": []},
     {"home": "A", "away": "B", "final": [1, 0], "events": [
         {"minute": 60, "type": "red", "team": "home", "player": "X"},
         {"minute": 75, "type": "goal", "team": "home", "player": "A1"}]}),
    ("F3", "omit_missing", "football_tin_tuc",
     "Viết tin: 'Nếu kịp hoàn tất đăng ký, cầu thủ này có thể đá chính.' "
     "Tiêu đề PHẢI giữ điều kiện 'nếu/có thể'.",
     {"forbid": [], "expect": [], "no_fab": ["trạng thái khẳng định (chưa/đang chờ)"]}),
]


def build_system(cfg, genre, vw):
    """cfg: raw | skill | min | full (skill=规则卡默认档,不注入 facts)"""
    if cfg == "raw":
        return "", None
    if cfg == "skill":
        p = vw.build_prompt(genre=genre)
        return p["system"], p
    p = vw.build_prompt(genre=genre)
    if cfg == "min":
        # chỉ nạp quy tắc tối thiểu: 1 file core, KHÔNG ví dụ, KHÔNG genre file
        core = vw.load_file(vw.CORE_FILE) if hasattr(vw, "CORE_FILE") else ""
        if not core:
            # fallback: lấy phần đầu của system (trước dấu phân cách đầu tiên)
            core = p["system"].split("\n\n---\n\n")[0]
        return core, p
    return p["system"], p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="eval/results")
    ap.add_argument("--cases", default="")
    ap.add_argument("--temperature", type=float, default=0.8)
    ap.add_argument("--max-tokens", type=int, default=3000)
    ap.add_argument("--tag", default="", help="nhãn mô hình (để so sánh nhiều model)")
    args = ap.parse_args()

    import llm_client
    import viet_writer as vw

    client = llm_client.LLMClient(None)   # None → 客户端自环境变量读取配置
    os.makedirs(args.out, exist_ok=True)
    tag = ("_" + args.tag) if args.tag else ""

    want = set(args.cases.split(",")) if args.cases else None
    index = []

    for case in CASES:
        cid, group, genre, prompt, rules = case[:5]
        case_facts = case[5] if len(case) > 5 else None
        if want and cid not in want:
            continue
        # 生成阶段注入事实块(仅 full,即"用 skill"的档;raw 不进,做对照)
        user_prompt = prompt
        # 三组对照:raw(无 skill) / skill(规则卡,不注入 facts) / full(规则卡 + facts)
        for cfg in ("raw", "skill", "full"):
            system, meta = build_system(cfg, genre, vw)
            if cfg == "skill":
                # 规则卡(默认档位)但不注入事实块 → 分离"规则卡"与"事实预处理"的贡献
                pass
            elif cfg == "full" and case_facts:
                try:
                    from prepare_facts import compute, format_for_prompt, check_input_text
                    _r = compute(case_facts)
                    _w = check_input_text(prompt, _r)
                    user_prompt = prompt + "\n\n" + format_for_prompt(_r, _w)
                except Exception as e:
                    user_prompt = prompt + f"\n\n[prepare_facts error: {e}]"
            else:
                user_prompt = prompt
            if system is None:
                system = ""
            t0 = time.time()
            try:
                res = client.chat(system, user_prompt, temperature=args.temperature,
                                  max_tokens=args.max_tokens)
                text, fr, usage = res.text, res.finish_reason, res.usage
            except Exception as e:
                text, fr, usage = f"[ERROR] {e}", "error", None
            dt = round(time.time() - t0, 1)

            # kiểm tra bẫy tự động (có nhận biết phủ định để tránh dương tính giả)
            low = text.lower()
            # phủ định có thể cách xa từ khóa (vd "không phải lời khuyên cá cược",
            # "không đưa lời khuyên cá cược"): chỉ cần một phủ định đứng trước
            NEG = ["không", "chẳng", "chưa", "đừng", "tránh"]
            def hit_neg(w):
                wl = w.lower()
                pos = 0
                while True:
                    i = low.find(wl, pos)
                    if i < 0:
                        return False
                    # xét 50 ký tự trước đó (đủ cho "không đưa lời khuyên cá cược")
                    ctx = low[max(0, i - 50):i]
                    if not any(n in ctx for n in NEG):
                        return True
                    pos = i + len(wl)
            hit_forbid = [w for w in rules["forbid"] if hit_neg(w)]

            # expect:khớp linh hoạt —— "chưa xác nhận" cũng khớp "chưa được xác nhận",
            # tránh âm tính giả do khác biệt hư từ nhỏ.
            import re as _re
            def hit_expect(w):
                wl = w.lower()
                # cho phép chèn tối đa 2 từ (không khoảng trắng) giữa các âm tiết
                parts = [ _re.escape(p) for p in wl.split() ]
                pat = r"\b" + r"\W+(?:\w+\W+){0,2}".join(parts)
                return _re.search(pat, low) is not None
            hit_expect_list = [w for w in rules["expect"] if hit_expect(w)]

            # Gọi bộ phát hiện dữ kiện bịa (nếu ca có 'no_fab'):
            # đếm nghi vấn thuộc các nhóm bị cấm; >0 nghĩa là KHÔNG đạt.
            fab_violations = []
            no_fab = rules.get("no_fab", [])
            if no_fab and fr != "error":
                try:
                    from check_fabrication import find_fabrications
                    found = find_fabrications(prompt, text)
                    fab_violations = [f["khớp"] for f in found if f["nhóm"] in no_fab]
                except Exception as e:
                    fab_violations = [f"[detector error: {e}]"]

            # D1: 风格检查(赛果组用;传 facts 才能跑 S1/S9)
            style_issues = []
            if group == "ket_qua" and fr != "error":
                try:
                    from check_style import check as style_check
                    style_issues = [i["rule"] for i in style_check(text, case_facts)]
                except Exception:
                    pass

            rec = {
                "id": cid, "group": group, "genre": genre, "config": cfg,
                "chars": len(text), "seconds": dt, "finish_reason": fr,
                "usage": usage, "forbidden_hit": hit_forbid,
                "expected_hit": hit_expect_list, "output": text,
                "style_issues": style_issues,
                "fabrication_violations": fab_violations,
                "_has_expect": bool(rules["expect"]),
                "_has_no_fab": bool(no_fab),
            }
            fn = f"{cid}_{cfg}{tag}.json"
            with open(os.path.join(args.out, fn), "w", encoding="utf-8") as f:
                json.dump(rec, f, ensure_ascii=False, indent=2)
            index.append({k: rec[k] for k in
                          ("id", "group", "genre", "config", "chars", "seconds",
                           "finish_reason", "forbidden_hit", "expected_hit")})
            flag = ""
            if hit_forbid:
                flag = "  ⚠ VI PHẠM: " + ", ".join(hit_forbid)
            print(f"  {cid}/{cfg:4s}  {len(text):5d} chars  {dt:5.1f}s  fr={fr}{flag}")

    with open(os.path.join(args.out, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
    print(f"\nĐã lưu {len(index)} kết quả -> {args.out}/")


if __name__ == "__main__":
    main()
