#!/usr/bin/env python3
"""通用体裁批量质量抽检:对每个体裁生成 1 篇,自动打分 + 人工可读摘要。

目的:20 张规则卡是从范文自动提炼的,未经验证。本脚本给出可读证据,
让用户判断"这个体裁能不能用",而不是只看"注入成功了"。

自动检查(不调模型,纯规则):
  - 汉字残留 / markdown 残留
  - 是否写成"清单"而不是文章(规则卡被逐条复述的典型症状)
  - 开头是否为元说明(「Dưới đây là...」「Bài viết này sẽ...」)
  - 长度是否落在合理区间(150-3000 字符)
  - 越南语声调字符比例(判断是否真越南语)

用法:
  python bin/audit_generic_quality.py --all --out eval/results/generic_audit
  python bin/audit_generic_quality.py --genres am_thuc tai_chinh
"""
import argparse
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "bin"))
sys.path.insert(0, os.path.join(ROOT, "src"))

import viet_writer as vw  # noqa: E402
import llm_client  # noqa: E402

# 每个体裁一个真实感的写作任务(越南语)
TASKS = {
    "van_hoc": "Viết một đoạn truyện ngắn về một người bà ở làng quê",
    "van_hoa_phong_tuc": "Viết bài về phong tục cúng ông Táo ngày 23 tháng Chạp",
    "nghe_thuat": "Viết bài về sự phát triển của hội họa Việt Nam đương đại",
    "ton_giao": "Viết bài giới thiệu về chùa Một Cột",
    "doi_song": "Viết bài về áp lực đồng trang lứa của người trẻ thành thị",
    "giai_tri": "Viết bài về sự trở lại của phim Việt tại phòng vé",
    "am_thuc": "Viết bài giới thiệu về phở Hà Nội",
    "du_lich": "Viết bài giới thiệu du lịch Hà Giang mùa lúa chín",
    "cong_viec": "Viết bài về kỹ năng quản lý thời gian cho người đi làm",
    "lich_su": "Viết bài về chiến thắng Bạch Đằng năm 1288",
    "dia_ly": "Viết bài về đặc điểm địa lý đồng bằng sông Cửu Long",
    "di_san": "Viết bài về di sản nhã nhạc cung đình Huế",
    "quan_su": "Viết bài về huấn luyện tác chiến trên biển",
    "the_che": "Viết bài về cải cách hành chính cấp xã",
    "y_te": "Viết bài về tầm quan trọng của tiêm chủng định kỳ",
    "tai_chinh": "Viết bài phân tích về lãi suất tiết kiệm tăng",
    "cong_nghe": "Viết bài về ứng dụng trí tuệ nhân tạo trong giáo dục",
    "hoc_thuat": "Viết bài giới thiệu một nghiên cứu về vi sinh vật biển",
    "phap_luat": "Viết bài giải thích quy định về hợp đồng lao động",
    "giao_duc": "Viết bài về đổi mới phương pháp dạy học ở trường phổ thông",
}

HAN_RE = re.compile(r"[\u4e00-\u9fff]")
MD_RE = re.compile(r"\*\*|^#{1,3}\s|^- ", re.M)
META_OPEN_RE = re.compile(
    r"^(Dưới đây là|Bài viết này|Trong bài viết này|Sau đây là|"
    r"Chúng ta sẽ cùng|Hãy cùng)", re.I)
VI_CHAR_RE = re.compile(r"[ăâđêôơưàáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩịòóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]", re.I)

# 法律/学术/制度类体裁天然使用编号标题和项目列表(`**1. …**`、`* …`)。
# 这些属于规范文体,不应判为"markdown 残留"或"清单体"。
STRUCTURED_GENRES = {"phap_luat", "hoc_thuat", "the_che", "y_te", "giao_duc"}


def audit(text, genre=None):
    issues = []
    L = len(text)
    structured = genre in STRUCTURED_GENRES
    if HAN_RE.search(text):
        issues.append(f"含汉字:{''.join(HAN_RE.findall(text))[:5]}")
    if MD_RE.search(text) and not structured:
        issues.append("markdown 残留")
    if META_OPEN_RE.search(text.strip()[:80]):
        issues.append("开头是元说明")
    if L < 150:
        issues.append(f"过短({L})")
    if L > 3000:
        issues.append(f"过长({L})")
    vi_ratio = len(VI_CHAR_RE.findall(text)) / max(L, 1)
    if vi_ratio < 0.08:
        issues.append(f"越南语声调比例低({vi_ratio:.2f})")
    # 逐条复述规则的特征:大量行以 "- " 开头(规范文体豁免)
    dash_lines = len([ln for ln in text.splitlines() if ln.strip().startswith(("-", "+", "*"))])
    if dash_lines >= 5 and not structured:
        issues.append(f"疑似清单体({dash_lines} 行)")
    return issues


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--genres", nargs="*", default=[])
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--out", default="eval/results/generic_audit")
    ap.add_argument("--tier", default="large")
    ap.add_argument("--max-tokens", type=int, default=1200)
    args = ap.parse_args()

    genres = list(TASKS) if args.all else args.genres
    if not genres:
        print("用 --all 或 --genres", file=sys.stderr)
        return 2

    client = llm_client.LLMClient(None)
    outdir = os.path.join(ROOT, args.out)
    os.makedirs(outdir, exist_ok=True)

    results = []
    for g in genres:
        task = TASKS.get(g, f"Viết một bài về chủ đề liên quan đến {g}")
        try:
            text = vw.write(client, task, genre=g, profile="full",
                           model_tier=args.tier,
                           gen_kw={"max_tokens": args.max_tokens, "temperature": 0.7})
        except Exception as e:
            print(f"  ✗ {g}: {type(e).__name__}: {e}")
            results.append({"genre": g, "error": f"{type(e).__name__}: {e}"})
            continue
        text = (text or "").strip()
        iss = audit(text, g)
        results.append({
            "genre": g, "task": task, "chars": len(text),
            "issues": iss, "ok": not iss, "text": text,
        })
        flag = "✓" if not iss else "⚠"
        print(f"  {flag} {g:20} {len(text):5}字符 {('; '.join(iss)) if iss else '正常'}")

    with open(os.path.join(outdir, "results.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    ok = sum(1 for r in results if r.get("ok"))
    print(f"\n{ok}/{len(results)} 无自动检出问题 → {outdir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
