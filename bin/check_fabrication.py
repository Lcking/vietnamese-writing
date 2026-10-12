#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_fabrication.py — Phát hiện "dữ kiện bịa" trong đầu ra tiếng Việt.

Vấn đề: mô hình tầm trung / mô hình nhỏ chạy prompt dài ('full') thường CHÈN
chi tiết cụ thể mà đề bài KHÔNG cung cấp, hoặc NỐI hai dữ kiện rời thành quan
hệ nhân quả mà nguồn không nói.

Đây là công cụ HỖ TRỢ (đánh dấu), KHÔNG phải quan toà tự động: kết quả là
danh sách NGHI VẤN để người đọc đối chiếu đề bài; phán quyết cuối cùng cần người.

Các nhóm phát hiện:
  - thời gian cụ thể      ("sáng nay", "một giờ đồng hồ")
  - hành động tổ chức     ("chính thức thông báo", "ban lãnh đạo quyết định")
  - bối cảnh sân đấu      ("khán đài", "khán giả")
  - con số / định lượng   ("2-0", "30%", năm)
  - TRẠNG THÁI KHẲNG ĐỊNH ("chưa được công bố", "đang chờ", "vẫn chưa rõ")
      → KHÔNG được miễn trừ bởi phủ định; chỉ bỏ qua nếu ĐỀ BÀI có cùng mô tả.
  - QUAN HỆ NHÂN QUẢ      ("do", "vì", "sau khi", "khiến", "dẫn đến")
      → hai mệnh đề nối bằng liên từ nhân quả, nếu đề bài không nêu cùng quan hệ.

Quy tắc giảm nhiễu:
  1. Phủ định CHỈ có tác dụng trong CÙNG MỘT CÂU (cắt theo .!?… và xuống dòng).
     Riêng nhóm 'trạng thái khẳng định' KHÔNG áp dụng quy tắc phủ định này.
  2. Chuẩn hoá trước khi so với đề bài: gạch ngang → '-', ngày bỏ 'ngày'/số 0 đầu,
     số bằng chữ (một..mười) → chữ số, bỏ khoảng trắng quanh tỉ số.

Dùng:
    python bin/check_fabrication.py --task "..." --text-file output.txt
    python bin/check_fabrication.py --scan-eval eval/results
"""
import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------- mẫu dữ kiện
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
        r"\b\d{1,2}\s*[-–]\s*\d{1,2}\b",       # tỉ số
        r"\b\d+(\.\d+)? ?(%|phần trăm)\b",
        r"\b\d+ (bàn|điểm|trận|năm|tháng|triệu|tỷ|nghìn)\b",
        r"\b(19|20)\d{2}\b",
    ]),
    # Nhóm đặc biệt: KHẲNG ĐỊNH TRẠNG THÁI "chưa có/đang chờ" — thường là bịa
    # khi đề bài chỉ đơn thuần KHÔNG cung cấp thông tin.
    ("trạng thái khẳng định (chưa/đang chờ)", [
        r"chưa (được )?(công bố|xác nhận|quyết định|thông báo|tiết lộ)",
        r"chưa có thông tin", r"chưa có kết quả", r"chưa rõ",
        r"đang chờ (xác nhận|kiểm tra|công bố)",
        r"vẫn chưa (rõ|xác nhận|công bố)", r"hiện chưa (có|xác nhận)",
    ]),
    # Nhóm đặc biệt: QUAN HỆ NHÂN QUẢ (bịa nguyên nhân/kết quả).
    ("quan hệ nhân quả", [
        r"\bdo\b", r"\bvì\b", r"\bbởi\b", r"\bsau khi\b",
        r"\bkhiến\b", r"\bdẫn đến\b", r"\bnên\b",
    ]),
]

# Nhóm KHÔNG được miễn trừ bởi phủ định (theo thiết kế ở trên)
NO_NEG_EXEMPT = {"trạng thái khẳng định (chưa/đang chờ)", "quan hệ nhân quả"}

NEG_WORDS = ["không", "chẳng", "đừng", "tránh", "thiếu"]

# ------------------------------------------------------------- chuẩn hoá so sánh
_DIGIT_WORDS = {
    "không": "0", "một": "1", "hai": "2", "ba": "3", "bốn": "4", "tư": "4",
    "năm": "5", "sáu": "6", "bảy": "7", "tám": "8", "chín": "9", "mười": "10",
}


def normalize(s):
    """Chuẩn hoá để so khớp: gạch ngang, ngày, số chữ, khoảng trắng, hư từ nhỏ."""
    if not s:
        return ""
    x = unicodedata.normalize("NFC", s).lower()
    x = x.replace("–", "-").replace("—", "-")        # gạch ngang → '-'
    x = re.sub(r"\bngày\s+", "", x)                   # bỏ 'ngày' trong ngày tháng
    x = re.sub(r"\b0(\d)\b", r"\1", x)                # 03/12 → 3/12
    # số bằng chữ → chữ số (chỉ tách từ đơn)
    x = re.sub(r"\b(" + "|".join(_DIGIT_WORDS) + r")\b",
               lambda m: _DIGIT_WORDS[m.group(1)], x)
    # Bỏ hư từ không đổi nghĩa: "được" (bị động/khả năng) — để "chưa xác nhận"
    # và "chưa được xác nhận" được coi là tương đương.
    x = re.sub(r"\bđược\s+", "", x)
    x = re.sub(r"(\d)\s*-\s*(\d)", r"\1-\2", x)       # 2 - 0 → 2-0
    x = re.sub(r"\s+", " ", x).strip()
    return x


def split_sentences(text):
    """Cắt câu theo .!?… và xuống dòng. Trả về (câu, vị_trí_bắt_đầu)."""
    out = []
    start = 0
    for m in re.finditer(r"[.!?…\n]+", text):
        seg = text[start:m.end()]
        if seg.strip():
            out.append((seg, start))
        start = m.end()
    if start < len(text) and text[start:].strip():
        out.append((text[start:], start))
    return out


def _sentence_containing(sents, pos):
    for seg, start in sents:
        if start <= pos < start + len(seg):
            return seg
    return ""


def _negated_in_sentence(sentence, frag_pos_in_sentence, window=50):
    """Phủ định CHỈ có tác dụng trong cùng câu."""
    seg = sentence[:frag_pos_in_sentence].lower()
    return any(n in seg[-window:] for n in NEG_WORDS)


def find_fabrications(task, text):
    """Trả về list chip nghi vấn: {nhóm, khớp, ngữ cảnh, trong_đề_bài, lý_do}."""
    findings = []
    if not text:
        return findings
    task_norm = normalize(task or "")
    sents = split_sentences(text)
    seen = set()

    for label, pats in PATTERNS:
        for pat in pats:
            for m in re.finditer(pat, text, flags=re.IGNORECASE):
                frag = m.group(0)
                key = (label, normalize(frag))
                if key in seen:
                    continue

                sent = _sentence_containing(sents, m.start())
                # vị trí tương đối trong câu:
                rel = m.start()
                for seg, start in sents:
                    if start <= m.start() < start + len(seg):
                        rel = m.start() - start
                        break

                # (1) Nhóm trạng thái/nhân quả: KHÔNG miễn trừ bởi phủ định.
                #     Chỉ bỏ nếu ĐỀ BÀI có cùng mô tả (chuẩn hoá).
                if label in NO_NEG_EXEMPT:
                    in_task = normalize(frag) in task_norm
                    # với nhân quả, cần cả liên từ xuất hiện trong đề bài
                    if label == "quan hệ nhân quả":
                        in_task = normalize(frag) in task_norm
                    if in_task:
                        seen.add(key)
                        continue
                    ctx = text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
                    reason = ("trạng thái khẳng định không có trong đề bài"
                              if label.startswith("trạng thái")
                              else "liên từ nhân quả không có trong đề bài")
                    findings.append({
                        "nhóm": label, "khớp": frag,
                        "ngữ cảnh": ctx, "trong_đề_bài": False, "lý_do": reason,
                    })
                    seen.add(key)
                    continue

                # (2) Nhóm thường: miễn trừ nếu phủ định CÙNG CÂU.
                if _negated_in_sentence(sent, rel):
                    seen.add(key)
                    continue

                # (3) Bỏ nếu mảnh này đã có trong đề bài (so sánh chuẩn hoá).
                if normalize(frag) in task_norm:
                    seen.add(key)
                    continue

                ctx = text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
                findings.append({
                    "nhóm": label, "khớp": frag,
                    "ngữ cảnh": ctx, "trong_đề_bài": False, "lý_do": "không có trong đề bài",
                })
                seen.add(key)
    return findings


def report(task, text, model=""):
    fs = find_fabrications(task, text)
    print(f"\n{'='*68}")
    if model:
        print(f"Mô hình: {model}")
    print(f"Độ dài đầu ra: {len(text)} ký tự")
    print(f"Nghi vấn cần đối chiếu: {len(fs)}")
    print(f"{'='*68}")
    if not fs:
        print("→ Không thấy dữ kiện nào ngoài đề bài. (Vẫn cần người đọc xác nhận.)")
        return fs
    by = {}
    for f in fs:
        by.setdefault(f["nhóm"], []).append(f)
    for label, items in by.items():
        print(f"\n▸ {label}:")
        for f in items:
            print(f"   • \"{f['khớp']}\"  ({f['lý_do']})")
            print(f"     ...{f['ngữ cảnh']}...")
    print(f"\n※ Đây là ĐÁNH DẤU, không phải kết luận. Hãy đối chiếu từng mục với đề bài.")
    return fs


def scan_eval(results_dir):
    results_dir = Path(results_dir)
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
        novel = find_fabrications(tasks.get(cid, ""), out)
        if novel:
            flagged.append((fp.name, len(novel), sorted({f["nhóm"] for f in novel})))

    print(f"\n{'='*68}\nQUÉT KẾT QUẢ EVAL: {len(files)} file\n{'='*68}")
    if not flagged:
        print("→ Không file nào có dấu hiệu bịa dữ kiện ngoài đề.")
        return
    for name, n, groups in flagged:
        print(f"  ⚠ {name:40s} {n:2d} nghi vấn  [{', '.join(groups)}]")
    print(f"\nTổng: {len(flagged)}/{len(files)} file có nghi vấn.")


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
