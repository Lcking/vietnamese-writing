#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clean_examples.py — Dọn NHIỄU trong examples/football/*.jsonl (không xoá cả bài).

Nguồn WanJuan là văn bản cào web đã làm sạch, nhưng phần thân vẫn sót MẨU
metadata của trang gốc: dấu thời gian, tên tác giả, dòng "Nguồn:", nhãn chuyên
mục. Những mẩu này nằm GIỮA bài, không phải nội dung.

Nguyên tắc:
  - CHỈ cắt mẩu metadata ĐỘC LẬP (thường ở đầu dòng); KHÔNG đụng tới ngày tháng
    nằm TRONG CÂU (ví dụ "kết thúc vào ngày 30/6/2024" là nội dung, giữ nguyên).
  - Không xoá cả bài; chỉ sửa trường `content`.
  - Ghi trường `_noise_removed: true` cho bài bị sửa, để hậu kiểm.

Dùng:
    python bin/clean_examples.py --dir examples/football            # dry-run
    python bin/clean_examples.py --dir examples/football --apply    # ghi đè
    python bin/clean_examples.py --dir examples/football --apply --report /tmp/clean.jsonl
"""
import argparse
import glob
import json
import os
import re

# Mỗi mục: (regex, thay thế). Chỉ khớp mẩu metadata ĐỘC LẬP.
CLEAN = [
    # "Thứ hai, 05/11/2018, 10:04" / "Thứ 2, 5/11/2018" — BẮT BUỘC có ngày SỐ ngay sau
    (re.compile(r"^\s*(Thứ\s*(hai|ba|tư|năm|sáu|bảy)|Chủ\s*nhật)\s*[,\s]\s*\d{1,2}[/-]\d{1,2}[/-]\d{4}[,\s]*\d{1,2}:\d{2}\s*$", re.I | re.M), ""),
    # "05:38, 14/01/2024"
    (re.compile(r"^\s*\d{1,2}:\d{2}[,\s]+\d{1,2}/\d{1,2}/\d{4}\s*$", re.M), ""),
    # "30/12/2019, 08:51"
    (re.compile(r"^\s*\d{1,2}/\d{1,2}/\d{4}[,\s]+\d{1,2}:\d{2}\s*$", re.M), ""),
    # "2022-11-25 11:54"
    (re.compile(r"^\s*\d{4}-\d{2}-\d{2}\s+\d{1,2}:\d{2}(:\d{2})?\s*$", re.M), ""),
    # "Đăng ngày: 03/04/2014 11:35"
    (re.compile(r"^\s*Đăng ngày:\s*[\d/: ]+\s*$", re.I | re.M), ""),
    # "Anh Nguyễn | 07:30 01/10/2018"
    (re.compile(r"^\s*[A-ZÀ-Ỹ][\wà-ỹ]*(?:\s+[A-ZÀ-Ỹ][\wà-ỹ]*){0,3}\s*\|\s*\d{1,2}:\d{2}\s*\d{1,2}/\d{1,2}/\d{4}\s*$", re.M), ""),
    # "Tổng hợp - 23/12/2017 07:45"
    (re.compile(r"^\s*Tổng hợp\s*[-–]\s*\d{1,2}/\d{1,2}/\d{4}[,\s]*[\d:]*\s*$", re.I | re.M), ""),
    # "P.A (Nguồn: HTV/NEXTSPORTS) |"  -> bỏ mẩu "(Nguồn: ...)" CHỈ khi ngắn, ngoặc
    (re.compile(r"\(\s*Nguồn:\s*[^)\n]{1,40}\)"), ""),
    # "Theo SohaNews" / "Theo Tiến Long ([Tên nguồn])" ở CUỐI BÀI
    (re.compile(r"\n\s*Theo\s+[^\n.]{1,30}(\(\[Tên nguồn\]\))?\s*$", re.I), ""),
    (re.compile(r"\n\s*\[Tên nguồn\]\s*$", re.I), ""),
    # "Nguồn: Bóng đá TV, Thể thao TV (VTVcab)" — CHỈ khi ở CUỐI và ngắn, không phân câu
    (re.compile(r"\n\s*Nguồn:\s*[^\n.]{1,50}\s*$", re.I), ""),
    # "Nguồn: [Link nguồn]" (kể cả lặp) và "[Link nguồn]"
    (re.compile(r"\[Link nguồn\]", re.I), ""),
    (re.compile(r"\n\s*Nguồn:\s*$", re.I | re.M), ""),
    # "ĐỌC THÊM – Nguồn: ..." -> bỏ tiền tố nhãn
    (re.compile(r"^\s*ĐỌC THÊM\s*[-–]\s*", re.I | re.M), ""),
    # "Theo Duy Luân - Zing.vn | 09:43 13/06/2022" (cuối bài)
    (re.compile(r"\n\s*Theo\s+[^\n]{1,40}\|\s*\d{1,2}:\d{2}\s*\d{1,2}/\d{1,2}/\d{4}\s*$", re.I), ""),
    # "P.A (Nguồn: HTV/NEXTSPORTS) |" — mẩu Nguồn trong ngoặc kèm dấu |
    (re.compile(r"\(\s*Nguồn:\s*[^)\n]{1,40}\)\s*\|?"), ""),
    # "Nguồn: [Link nguồn]" lặp — dọn các nhãn rỗng
    (re.compile(r"\n\s*Nguồn:\s*(Nguồn:)?\s*$", re.I | re.M), ""),
    # "Nguồn: " đứng đầu dòng nhưng theo sau là NỘI DUNG -> chỉ bỏ nhãn, giữ nội dung
    (re.compile(r"^\s*Nguồn:\s+(?=\S)", re.I | re.M), ""),
]


def clean_one(content):
    orig = content
    text = content
    for pat, rep in CLEAN:
        text = pat.sub(rep, text)
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, (text != orig)


def main():
    ap = argparse.ArgumentParser(description="Dọn nhiễu metadata trong examples jsonl")
    ap.add_argument("--dir", required=True, help="Thư mục chứa *.jsonl")
    ap.add_argument("--apply", action="store_true", help="Ghi đè (mặc định chỉ dry-run)")
    ap.add_argument("--report", default=None, help="Ghi danh sách bài bị sửa ra file")
    ap.add_argument("--skip", default="", help="Tên file bỏ qua (phân tách bằng dấu phẩy)")
    args = ap.parse_args()

    skip = set(s.strip() for s in args.skip.split(",") if s.strip())
    total_files = total_changed = total_rows = 0
    report = []

    for fp in sorted(glob.glob(os.path.join(args.dir, "*.jsonl"))):
        if os.path.basename(fp) in skip:
            continue
        rows = [json.loads(l) for l in open(fp, encoding="utf-8") if l.strip()]
        changed = 0
        for r in rows:
            nc, ch = clean_one(r.get("content", ""))
            if ch:
                r["_noise_removed"] = True
                r["_orig_content_len"] = len(r.get("content", ""))
                r["content"] = nc
                if "len" in r:
                    r["len"] = len(nc)
                changed += 1
                report.append({"file": os.path.basename(fp),
                               "title": r.get("title", "")[:70],
                               "before": r["_orig_content_len"], "after": len(nc)})
        total_files += 1
        total_rows += len(rows)
        if changed:
            total_changed += changed
            print(f"  {os.path.basename(fp):32s} sửa {changed}/{len(rows)} bài")
            if args.apply:
                with open(fp, "w", encoding="utf-8") as f:
                    for r in rows:
                        f.write(json.dumps(r, ensure_ascii=False) + "\n")

    mode = "ĐÃ GHI" if args.apply else "DRY-RUN (thêm --apply để ghi)"
    print(f"\n[{mode}] {total_files} file, {total_rows} bài, sửa {total_changed} bài")
    if args.report:
        with open(args.report, "w", encoding="utf-8") as f:
            for d in report:
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
        print(f"Báo cáo -> {args.report}")


if __name__ == "__main__":
    main()
