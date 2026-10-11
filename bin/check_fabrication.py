#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_fabrication.py — Phát hiện "dữ kiện bịa" trong đầu ra tiếng Việt.

Vấn đề: mô hình tầm trung / mô hình nhỏ chạy prompt dài (cấu hình 'full')
thường CHÈN các chi tiết cụ thể mà đề bài KHÔNG hề cung cấp — ví dụ:
  - mốc thời gian ("sáng nay", "trưa nay", "chiều mai", "một giờ đồng hồ")
  - hành động của tổ chức ("chính thức xác nhận", "ban lãnh đạo quyết định")
  - bối cảnh sân đấu ("khán đài rộn ràng", "khán giả", "tiếng cổ vũ")
  - con số / tỉ số / tên riêng không có trong đề

Đây là công cụ HỖ TRỢ, KHÔNG phải quan toà tự động:
  - Nó KHÔNG kết luận "đúng/sai". Nó ĐÁNH DẤU những chỗ NGHI VẤN để người
    đọc đối chiếu với đề bài. Việc phán quyết cuối cùng vẫn cần con người.

Dùng:
    python bin/check_fabrication.py \\
        --task "Viết bản tin: CLB Hà Nội bổ nhiệm HLV mới. Không nêu tên cụ thể." \\
        --text-file output.txt

    # hoặc chấm hàng loạt kết quả eval:
    python bin/check_fabrication.py --scan-eval eval/results
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---- Mẫu dữ kiện cụ thể (thường bị bịa) ----
# Mỗi nhóm: (nhãn, danh sách regex tiếng Việt)
PATTERNS = [
    ("thời gian cụ thể", [
        r"\bsáng nay\b", r"\btrưa nay\b", r"\bchiều nay\b", r"\btối nay\b",
        r"\bchiều mai\b", r"\bsáng mai\b", r"\btối mai\b", r"\bngày mai\b",
        r"\bhôm qua\b", r"\btuần sau\b", r"\btuần trước\b", r"\bvài ngày\b",
        r"\bmột giờ đồng hồ\b", r"\bvài giờ\b", r"\btrong \d+ (giờ|ngày|tuần)\b",
        r"\b(hôm|ngày) \d{1,2}/\d{1,2}\b",
    ]),
    ("hành động tổ chức", [
        r"chính thức (xác nhận|thông báo|công bố)",
        r"ban lãnh đạo (quyết định|đưa ra|họp)",
        r"(đã|vừa) (ký|hoàn tất|chốt)",
        r"cuộc họp nội bộ", r"buổi họp báo",
        r"ra mắt (trong|vào)", r"thông báo được đưa ra",
    ]),
    ("bối cảnh sân đấu / khán giả", [
        r"khán đài", r"khán giả", r"tiếng cổ vũ", r"tiếng reo",
        r"cổ động viên", r"bầu không khí", r"trên sân cỏ",
        r"người hâm mộ (phấn khích|vỡ oà|nín thở)",
    ]),
    ("con số / định lượng cụ thể", [
        r"\b\d{1,2}[-–]\d{1,2}\b",          # tỉ số
        r"\b\d+(\.\d+)? ?(%|phần trăm)\b",
        r"\b\d+ (bàn|điểm|trận|năm|tháng|triệu|tỷ|nghìn)\b",
        r"\b(19|20)\d{2}\b",                 # năm (không bắt mọi số 4 chữ số)
    ]),
]

# Từ phủ định phía trước → nghĩa là model ĐANG TỪ CHỐI bịa (không tính)
NEG_PREFIX = ["không", "chưa", "chẳng", "đừng", "tránh", "thiếu", "không có",
              "chưa có", "không nêu", "không xác nhận", "không được"]


def _negated(text_low, pos, window=60):
    return any(n in text_low[max(0, pos - window):pos] for n in NEG_PREFIX)


def find_fabrications(task, text):
    """Trả về list các chip nghi vấn: {nhóm, khớp, ngữ cảnh, trong_đề_bài}."""
    findings = []
    text_low = text.lower()
    task_low = (task or "").lower()
    seen = set()

    for label, pats in PATTERNS:
        for pat in pats:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                frag = m.group(0)
                key = (label, frag.lower())
                if key in seen:
                    continue
                # nằm sau phủ định → model đang từ chối, không tính
                if _negated(text_low, m.start()):
                    continue
                # nếu mảnh này CÓ trong đề bài → không phải bịa
                in_task = frag.lower() in task_low
                ctx = text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
                findings.append({
                    "nhóm": label,
                    "khớp": frag,
                    "ngữ cảnh": ctx,
                    "trong_đề_bài": in_task,
                })
                seen.add(key)
    return findings


def report(task, text, model=""):
    fs = find_fabrications(task, text)
    novel = [f for f in fs if not f["trong_đề_bài"]]
    print(f"\n{'='*68}")
    if model:
        print(f"Mô hình: {model}")
    print(f"Độ dài đầu ra: {len(text)} ký tự")
    print(f"Nghi vấn cần đối chiếu: {len(novel)} (tổng bắt được {len(fs)})")
    print(f"{'='*68}")
    if not novel:
        print("→ Không thấy dữ kiện cụ thể nào ngoài đề bài. (Vẫn cần người đọc xác nhận.)")
        return novel
    by = {}
    for f in novel:
        by.setdefault(f["nhóm"], []).append(f)
    for label, items in by.items():
        print(f"\n▸ {label}:")
        for f in items:
            print(f"   • \"{f['khớp']}\"")
            print(f"     ...{f['ngữ cảnh']}...")
    print(f"\n※ Đây là ĐÁNH DẤU, không phải kết luận. Hãy đối chiếu từng mục với đề bài")
    print(f"  và xác nhận thủ công. Model từ chối bịa sẽ dùng từ phủ định (đã bỏ qua).")
    return novel


def scan_eval(results_dir):
    """Quét toàn bộ kết quả eval, đối chiếu đề bài nếu tìm thấy."""
    results_dir = Path(results_dir)
    # nạp đề bài từ run_eval.CASES nếu có
    tasks = {}
    try:
        sys.path.insert(0, str(ROOT / "bin"))
        import run_eval
        for cid, _g, _genre, prompt, _rules in run_eval.CASES:
            tasks[cid] = prompt
    except Exception as e:
        print(f"(không nạp được đề bài từ run_eval: {e})")

    files = sorted(results_dir.glob("*.json"))
    flagged = []
    for fp in files:
        if fp.name in ("index.json",):
            continue
        try:
            d = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        out = d.get("output", "")
        cid = d.get("id", "")
        if not out or d.get("finish_reason") == "error":
            continue
        task = tasks.get(cid, "")
        novel = [f for f in find_fabrications(task, out) if not f["trong_đề_bài"]]
        if novel:
            flagged.append((fp.name, len(novel), sorted({f["nhóm"] for f in novel})))

    print(f"\n{'='*68}\nQUÉT TOÀN BỘ KẾT QUẢ EVAL: {len(files)} file\n{'='*68}")
    if not flagged:
        print("→ Không file nào có dấu hiệu bịa dữ kiện ngoài đề.")
        return
    for name, n, groups in flagged:
        print(f"  ⚠ {name:40s} {n:2d} nghi vấn  [{', '.join(groups)}]")
    print(f"\nTổng: {len(flagged)}/{len(files)} file có nghi vấn. Xem chi tiết từng file bằng --text-file.")


def main():
    ap = argparse.ArgumentParser(description="Phát hiện dữ kiện bịa trong đầu ra tiếng Việt")
    ap.add_argument("--task", help="Đề bài gốc (để đối chiếu)")
    ap.add_argument("--text-file", help="File chứa đầu ra của mô hình")
    ap.add_argument("--text", help="Đầu ra trực tiếp (thay cho --text-file)")
    ap.add_argument("--scan-eval", help="Quét cả thư mục kết quả eval")
    args = ap.parse_args()

    if args.scan_eval:
        scan_eval(args.scan_eval)
        return

    text = args.text
    if args.text_file and not text:
        text = Path(args.text_file).read_text(encoding="utf-8")
    if not text:
        ap.error("Cần --text, --text-file, hoặc --scan-eval")
    report(args.task or "", text)


if __name__ == "__main__":
    main()
