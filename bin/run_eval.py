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
import argparse, json, os, sys, time, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "bin"))

# ---- các ca kiểm thử (khớp eval/evalset.md) ----
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
]


def build_system(cfg, genre, vw):
    """cfg: raw | min | full"""
    if cfg == "raw":
        return "", None
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

    for cid, group, genre, prompt, rules in CASES:
        if want and cid not in want:
            continue
        for cfg in ("raw", "min", "full"):
            system, meta = build_system(cfg, genre, vw)
            if system is None:
                system = ""
            t0 = time.time()
            try:
                res = client.chat(system, prompt, temperature=args.temperature,
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

            rec = {
                "id": cid, "group": group, "genre": genre, "config": cfg,
                "chars": len(text), "seconds": dt, "finish_reason": fr,
                "usage": usage, "forbidden_hit": hit_forbid,
                "expected_hit": hit_expect_list, "output": text,
                "_has_expect": bool(rules["expect"]),
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
