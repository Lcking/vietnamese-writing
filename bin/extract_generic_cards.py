#!/usr/bin/env python3
"""从 examples/generic/<genre>.jsonl 提炼写作规则卡 → references/cards/<genre>.md

设计要点:
  - 只读范文,不调模型打分(分数已在蒸馏时算过)
  - 任务切小:每个体裁单独一次调用,提示词要求输出结构化的小节
  - 关思考链(本地 Qwen 必须,否则正文被思考过程吃掉)
  - 输出 ≤1700 字符,符合 tests/test_card_length 的上限
  - 卡里不出现汉字(有测试卡这条)

用法:
  python bin/extract_generic_cards.py --genres am_thuc du_lich ...
  python bin/extract_generic_cards.py --all
  python bin/extract_generic_cards.py --all --dry-run   # 只打印提示词
"""
import argparse
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
sys.path.insert(0, os.path.join(ROOT, "src"))

GEN_EX = os.path.join(ROOT, "examples", "generic")
CARDS = os.path.join(ROOT, "references", "cards")

# 体裁名 → 越南语体裁说明(用于提示词)
GENRE_LABEL = {
    "van_hoc": "văn học / truyện kể (文学/叙事)",
    "van_hoa_phong_tuc": "văn hóa phong tục (风俗文化)",
    "nghe_thuat": "nghệ thuật (艺术)",
    "ton_giao": "tôn giáo tín ngưỡng (宗教)",
    "doi_song": "đời sống xã hội (社会生活)",
    "giai_tri": "giải trí (娱乐)",
    "am_thuc": "ẩm thực (美食)",
    "du_lich": "du lịch (旅游)",
    "cong_viec": "công việc nghề nghiệp (职场)",
    "lich_su": "lịch sử (历史)",
    "dia_ly": "địa lý (地理)",
    "di_san": "di sản văn hóa (文化遗产)",
    "quan_su": "quân sự quốc phòng (军事)",
    "the_che": "thể chế chính sách (制度政策)",
    "y_te": "y tế sức khỏe (医疗健康)",
    "tai_chinh": "tài chính kinh tế (财经)",
    "cong_nghe": "công nghệ (科技)",
    "hoc_thuat": "học thuật nghiên cứu (学术)",
    "phap_luat": "pháp luật (法律)",
    "giao_duc": "giáo dục (教育)",
}

PROMPT = """Bạn là biên tập viên tiếng Việt. Dưới đây là 6 đoạn văn mẫu thuộc thể loại **{label}**.

Nhiệm vụ: viết một "thẻ quy tắc" (rule card) ngắn gọn để người viết khác làm theo.

Yêu cầu BẮT BUỘC:
- Viết hoàn toàn bằng tiếng Việt. KHÔNG dùng chữ Hán, không dùng tiếng Anh (trừ thuật ngữ phổ biến).
- Chỉ viết những gì CÓ THỂ LÀM THEO và KIỂM TRA ĐƯỢC: cấu trúc, độ dài, cách mở đầu/kết thúc, từ ngữ nên và không nên dùng.
- KHÔNG viết đoạn giới thiệu, không giải thích lan man, không nhắc lại nội dung cụ thể của các mẫu.
- Tổng độ dài dưới 1500 ký tự.

Định dạng đầu ra (markdown, đúng các mục này):
# <Tên thể loại>

## Cấu trúc
- ...

## Độ dài
- ...

## Cách mở đầu
- ...

## Từ ngữ / giọng điệu
- ...

## Tránh
- ...

--- VĂN MẪU ---
{samples}
"""


def load_samples(genre, n=6, max_chars=900):
    fp = os.path.join(GEN_EX, f"{genre}.jsonl")
    if not os.path.exists(fp):
        return None
    rows = []
    with open(fp, encoding="utf-8") as f:
        for i, line in enumerate(f):
            if i >= n:
                break
            r = json.loads(line)
            c = (r.get("content") or "").strip()
            if len(c) < 200:
                continue
            rows.append(c[:max_chars])
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genres", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--force", action="store_true", help="覆盖已有卡")
    args = ap.parse_args()

    genres = list(GENRE_LABEL) if args.all else args.genres
    if not genres:
        print("请用 --all 或 --genres 指定体裁", file=sys.stderr)
        return 2

    client = None
    if not args.dry_run:
        import llm_client
        client = llm_client.LLMClient(None)

    os.makedirs(CARDS, exist_ok=True)
    done = skipped = failed = 0
    for g in genres:
        out = os.path.join(CARDS, f"{g}.md")
        if os.path.exists(out) and not args.force:
            print(f"  跳过 {g}: 已有卡(用 --force 覆盖)")
            skipped += 1
            continue
        samples = load_samples(g)
        if not samples:
            print(f"  跳过 {g}: 无范文")
            skipped += 1
            continue
        prompt = PROMPT.format(
            label=GENRE_LABEL.get(g, g),
            samples="\n\n".join(f"[Mẫu {i+1}]\n{s}" for i, s in enumerate(samples)),
        )
        if args.dry_run:
            print(f"=== {g} === ({len(prompt)} chars)")
            print(prompt[:400], "...\n")
            continue
        try:
            resp = client.chat(
                "Bạn là biên tập viên tiếng Việt chuyên viết quy tắc hướng dẫn.",
                prompt,
                max_tokens=2000, temperature=0.3, disable_thinking=True,
            )
            text = getattr(resp, "text", resp)
        except Exception as e:
            print(f"  ✗ {g}: {type(e).__name__}: {e}")
            failed += 1
            continue
        text = (text or "").strip()
        # 去掉可能的 ```markdown 包裹
        if text.startswith("```"):
            text = "\n".join(
                ln for ln in text.splitlines() if not ln.strip().startswith("```")
            ).strip()
        if len(text) < 200:
            print(f"  ✗ {g}: 输出过短({len(text)}),丢弃")
            failed += 1
            continue
        # 超长则在段落边界截断(不硬切)
        if len(text) > 1700:
            cut = text.rfind("\n##", 0, 1700)
            text = text[:cut].rstrip() if cut > 600 else text[:1700].rstrip()
        with open(out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"  ✓ {g}: {len(text)} chars → {os.path.basename(out)}")
        done += 1

    print(f"\n生成 {done} / 跳过 {skipped} / 失败 {failed}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
