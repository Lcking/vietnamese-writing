#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
viet_writer — 越南语写作引擎主入口

用法:
    python bin/viet_writer.py --task "viết bản tin MU thắng 3-1" --genre football_tin_tuc
    python bin/viet_writer.py --task "bình luận trận Việt Nam - Thái Lan"   # 自动识别足球
    python bin/viet_writer.py --task "..." --dump-prompt        # 只看提示词体积与入选样本,不调模型
    python bin/viet_writer.py --task "..." --dry-run            # 同 dump-prompt 的别名
    python bin/viet_writer.py --interactive

设计要点(对应评审 P1):
  - build_prompt() 是纯函数:只组装规则+范文,返回文本与元数据,不调用任何模型。
  - 预算分离:全局规则、场景规则、范文各有独立字符预算,超限时按语义边界截断并报告。
  - 显式体裁优先:--genre 给了就用;只有没给才自动识别;识别不出加载"最小通用规则",
    而不是把全部 7 个文体规范全塞进去。
  - 范文明确标注"仅参考表达、非事实",提示模型不要继承其中的姓名/比分/伤停。
  - 语言指导与输出合同分离:输出合同(JSON/纯文本/分段)由调用方通过 --format 指定,
    skill 不默认强制"只输出完整文章"。
"""
import os, sys, argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

REFERENCES = ROOT / "references"
EXAMPLES = ROOT / "examples"
PROMPTS = ROOT / "prompts"

# 所有可用体裁(显式指定时校验)
GENRES = ["van_hoc", "bao_chi", "bach_khoa", "cong_van",
          "mang_xa_hoi", "doi_song", "chuyen_mon",
          "football_thuat_ngu", "football_binh_luan", "football_tin_tuc",
          "football_chuyen_nhuong", "football_doi_tuyen", "football_nhan_vat",
          "football_pre_match", "football_analysis", "social_post"]

# 新增体裁对应的 reference 文件(有些新体裁复用已有规范文件)
GENRE_FILE = {
    "football_pre_match": "football_pre_match.md",
    "football_analysis": "football_analysis.md",
    "social_post": "social_post.md",
}

# ── 默认预算(字符)。可在 config 里覆盖。──
DEFAULT_BUDGET = {
    "core": 4000,        # system_vi_writer.md 核心指令
    "global": 18000,     # 全局维度规则(_global_*.md)合计上限
    "genre": 16000,      # 场景体裁规范上限
    "examples": 12000,   # few-shot 范文合计上限
}

FOOTBALL_HINTS = ["bóng đá", "bình luận", "trận đấu", "cầu thủ", "đội bóng",
                  "world cup", "champions league", "v-league", "aff cup",
                  "chuyển nhượng", "chiêu mộ", "ký hợp đồng", "bàn thắng",
                  "hlv", "huấn luyện viên", "tuyển việt nam", "đội tuyển",
                  "sea games", "ghi bàn", "thủ môn", "vòng loại", "penalty",
                  "tỷ số", "kết quả", "tiền đạo", "hậu vệ", "tiền vệ", "clb",
                  "câu lạc bộ", "giải bóng", "cúp", "sân vận động",
                  "足球", "解说", "比赛", "球队", "世界杯", "转会", "赛前", "前瞻",
                  "签约", "加盟", "前锋"]

# 各足球体裁对应的范文主题(可多个)
THEME_MAP = {
    "football_binh_luan": ["doi_tuyen_vn", "world_cup", "phan_tich_chien_thuat"],
    "football_tin_tuc": ["world_cup", "ngoai_hang", "champions_league"],
    "football_chuyen_nhuong": ["chuyen_nhuong"],
    "football_doi_tuyen": ["doi_tuyen_vn", "chau_a"],
    "football_nhan_vat": ["ngoai_hang", "world_cup", "doi_tuyen_vn"],
    "football_thuat_ngu": ["phan_tich_chien_thuat"],
    "football_pre_match": ["doi_tuyen_vn", "chau_a", "world_cup"],
    "football_analysis": ["phan_tich_chien_thuat", "champions_league"],
    "social_post": ["social_post", "doi_tuyen_vn"],
}

EXAMPLE_HEADER = (
    "## Ví dụ mẫu (bài thật, CHỈ để tham khảo cách diễn đạt — KHÔNG phải dữ kiện)\n\n"
    "> Quan trọng: các ví dụ dưới đây là bài báo cũ, chỉ dùng để học **cách hành văn, "
    "từ ngữ, nhịp điệu**. TUYỆT ĐỐI không sao chép hoặc kế thừa tên người, tỷ số, "
    "tình hình chấn thương, mốc thời gian hay kết luận của chúng vào bài mới.\n\n"
)


def load_file(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""


def _truncate_semantic(text, budget):
    """按段落/句子边界截断到 budget 字符内。返回 (截断后文本, 是否截断)。"""
    if len(text) <= budget:
        return text, False
    cut = text[:budget]
    # 优先回退到最后一个段落边界,其次句子边界
    for sep in ("\n\n", "\n", ". ", "。 "):
        idx = cut.rfind(sep)
        if idx > budget * 0.5:
            return cut[:idx].rstrip(), True
    return cut.rstrip(), True


def _is_clean_title(title):
    """标题噪声过滤:排除混入机构名、广告、赌博关键词的标题。"""
    import re
    bad = re.compile(
        r"(bắn cá|đổi thưởng|casino|soi cầu|đánh bài|cá độ|nhà cái|fun88|w88|m88"
        r"|tài xỉu online|game bài|lô đề|khuyến mãi|tạp chí|liên hệ quảng cáo"
        r"|http|www\.|\d{4,}|xem thêm|đọc tiếp|theo dõi|hotline)", re.I)
    if bad.search(title):
        return False
    # 标题里出现"—"后跟疑似站点名的（长尾 SEO 标题）也排除
    if title.count("-") >= 2 and len(title) > 90:
        return False
    return True


def pick_examples(genre, budget=None):
    """为足球体裁挑选范文。返回 (范文文本, 元数据列表)。
    按配置的预算在"完整语义边界"选取,不做生硬的前 N 条截断。"""
    budget = budget if budget is not None else DEFAULT_BUDGET["examples"]
    dirs = THEME_MAP.get(genre, [])
    chunks, meta, used = [], [], 0
    seen_titles = set()
    for d in dirs:
        fp = EXAMPLES / "football" / f"{d}.jsonl"
        if not fp.exists():
            continue
        for line in fp.read_text(encoding="utf-8").splitlines():
            if used >= budget:
                break
            try:
                r = json.loads(line)
            except Exception:
                continue
            title = (r.get("title") or "").strip()
            if title in seen_titles or not _is_clean_title(title):      # 去重 + 噪声过滤
                continue
            content = (r.get("content") or "").strip()
            if not content:
                continue
            block = f"[{title}]\n{content[:1500]}"
            if used + len(block) > budget:
                continue
            seen_titles.add(title)
            chunks.append(block)
            used += len(block)
            meta.append({"theme": d, "title": title[:80],
                         "source_url": r.get("source_url"),
                         "content_sha256": (r.get("content_sha256") or "")[:12]})
        if used >= budget:
            break
    return "\n\n---\n\n".join(chunks), meta


def detect_genre(task):
    """从任务描述自动识别体裁。仅在未显式指定 --genre 时作为回退。"""
    t = task.lower()
    is_fb = any(h in t for h in FOOTBALL_HINTS)
    if is_fb:
        if any(k in t for k in ["chuyển nhượng", "转会", "chiêu mộ", "ký hợp đồng"]):
            return "football_chuyen_nhuong"
        if any(k in t for k in ["soi kèo", "nhận định", "tài xỉu", "trước trận",
                                "赛前", "前瞻", "dự đoán"]):
            return "football_pre_match"
        if any(k in t for k in ["phân tích", "chiến thuật", "分析", "战术"]):
            return "football_analysis"
        if any(k in t for k in ["bản tin", "新闻", "kết quả", "tỷ số"]):
            return "football_tin_tuc"
        if any(k in t for k in ["chân dung", "tiểu sử", "人物", "cầu thủ", "hlv"]):
            return "football_nhan_vat"
        if any(k in t for k in ["tuyển việt nam", "đội tuyển", "aff cup", "sea games"]):
            return "football_doi_tuyen"
        if any(k in t for k in ["thuật ngữ", "术语"]):
            return "football_thuat_ngu"
        if any(k in t for k in ["mạng xã hội", "status", "facebook", "社交", "帖子"]):
            return "social_post"
        return "football_binh_luan"   # 默认足球 = 解说
    if any(k in t for k in ["mạng xã hội", "facebook", "status", "社交"]):
        return "social_post"
    return None    # 无体裁:走最小通用规则


def build_prompt(genre=None, budget=None, examples=True, format_contract=None):
    """
    纯函数:组装提示词,不调用任何模型。
    返回 dict:
      { "system": str, "genre": str|None, "stats": {...}, "examples_meta": [...],
        "truncations": [...], "format_contract": str|None }
    """
    budget = {**DEFAULT_BUDGET, **(budget or {})}
    truncations = []
    parts = []

    # 1) 核心指令
    core = load_file(PROMPTS / "system_vi_writer.md")
    core, cut = _truncate_semantic(core, budget["core"])
    if cut:
        truncations.append(("core", budget["core"]))
    if core:
        parts.append(core)

    # 2) 全局规则(合计预算)
    gparts, gused = [], 0
    for f in sorted(REFERENCES.glob("_global_*.md")):
        txt = load_file(f)
        if not txt.strip():
            continue
        if gused + len(txt) > budget["global"]:
            remain = budget["global"] - gused
            if remain < 1500:      # 剩太少就整块跳过,不塞半截文件进来
                truncations.append((f.name, "skipped(global budget)"))
                continue
            txt, cut = _truncate_semantic(txt, remain)
            if cut:
                truncations.append((f.name, remain))
        gparts.append(txt)
        gused += len(txt)
    if gparts:
        parts.append("\n\n---\n\n".join(gparts))

    # 3) 场景体裁规则
    resolved_genre = genre
    examples_meta = []
    if resolved_genre and resolved_genre in GENRES:
        fname = GENRE_FILE.get(resolved_genre, f"{resolved_genre}.md")
        gtxt = load_file(REFERENCES / fname)
        if gtxt.strip():
            gtxt, cut = _truncate_semantic(gtxt, budget["genre"])
            if cut:
                truncations.append((fname, budget["genre"]))
            parts.append(gtxt)
        # 4) few-shot 范文(仅足球/社媒体裁)
        if examples and (resolved_genre.startswith("football_") or resolved_genre == "social_post"):
            ex, examples_meta = pick_examples(resolved_genre, budget["examples"])
            if ex:
                parts.append(EXAMPLE_HEADER + ex)
    else:
        # 无体裁:最小通用规则(只放核心 + 全局),不加载全部文体规范
        pass

    system = "\n\n---\n\n".join(p for p in parts if p.strip())
    genre_chars = 0
    if resolved_genre:
        gene_file = GENRE_FILE.get(resolved_genre, f"{resolved_genre}.md")
        genre_chars = len(load_file(REFERENCES / gene_file))
    examples_chars = 0
    stats = {
        "total_chars": len(system),
        "core_chars": len(core),
        "global_chars": gused,
        "genre_chars": genre_chars,
        "n_examples": len(examples_meta),
    }
    return {
        "system": system,
        "genre": resolved_genre,
        "stats": stats,
        "examples_meta": examples_meta,
        "truncations": truncations,
        "format_contract": format_contract,
    }


def build_user_prompt(task, genre=None, extra="", format_contract=None):
    lines = ["Yêu cầu viết:", task, ""]
    if genre:
        lines.append(f"Nhóm văn bản: {genre}")
    if extra:
        lines.append(extra)
    lines.append("")
    if format_contract:
        lines.append("Định dạng đầu ra do hệ thống gọi yêu cầu:")
        lines.append(format_contract)
    else:
        lines.append("Hãy viết bằng tiếng Việt tự nhiên, đúng phong cách, phù hợp với người đọc Việt Nam. "
                     "Chỉ trả về NỘI DUNG BÀI VIẾT, không giải thích.")
    return "\n".join(lines)


def write(client, task, genre=None, extra="", format_contract=None, gen_kw=None):
    """调用模型写作。genre 为 None 时自动识别。生成参数由 gen_kw 显式传入(否则用配置)。"""
    if genre is None:
        genre = detect_genre(task)
    prompt = build_prompt(genre, format_contract=format_contract)
    user = build_user_prompt(task, prompt["genre"], extra, format_contract)
    kw = dict(gen_kw or {})
    result = client.chat(prompt["system"], user, **kw)
    text = result.text if hasattr(result, "text") else str(result)
    setattr(write, "last_meta", {
        "genre": prompt["genre"],
        "finish_reason": getattr(result, "finish_reason", None),
        "truncated": getattr(result, "truncated", False),
        "usage": getattr(result, "usage", {}),
    })
    return text


def main():
    ap = argparse.ArgumentParser(description="越南语写作引擎")
    ap.add_argument("--task", "-t", help="写作任务(越南语或中文)")
    ap.add_argument("--genre", "-g", choices=GENRES, help="体裁(不填则自动识别;识别不出用最小通用规则)")
    ap.add_argument("--extra", "-e", default="", help="额外要求")
    ap.add_argument("--format", "-f", dest="format_contract", default=None,
                    help="输出合同(如 'trả về JSON {...}' 或 'chia 3 đoạn')。默认纯文章。")
    ap.add_argument("--config", "-c", help="配置文件路径(JSON/YAML)")
    ap.add_argument("--max-tokens", type=int, help="显式覆盖 max_tokens(优先于配置)")
    ap.add_argument("--temperature", type=float, help="显式覆盖 temperature")
    ap.add_argument("--dump-prompt", action="store_true", help="只打印提示词体积与实际入选样本,不调用模型")
    ap.add_argument("--dry-run", action="store_true", help="--dump-prompt 的别名")
    ap.add_argument("--interactive", "-i", action="store_true", help="交互模式")
    args = ap.parse_args()

    cfg = None
    if args.config:
        txt = Path(args.config).read_text(encoding="utf-8")
        if args.config.endswith((".yaml", ".yml")):
            try:
                import yaml; cfg = yaml.safe_load(txt)
            except ImportError:
                cfg = json.loads(txt)
        else:
            cfg = json.loads(txt)

    # 组装显式生成参数(未给则 None,由客户端按"配置>默认"决定)
    gen_kw = {}
    if args.max_tokens is not None:
        gen_kw["max_tokens"] = args.max_tokens
    if args.temperature is not None:
        gen_kw["temperature"] = args.temperature

    # dump-prompt 模式:不需要 API Key
    if args.dump_prompt or args.dry_run:
        if not args.task:
            ap.error("--dump-prompt 需要 --task")
        genre = args.genre or detect_genre(args.task)
        p = build_prompt(genre, format_contract=args.format_contract)
        print(f"任务: {args.task}")
        print(f"体裁: {p['genre'] or '(无 · 最小通用规则)'}")
        print(f"提示词总字符: {p['stats']['total_chars']:,}")
        print(f"  核心: {p['stats']['core_chars']:,} 字符")
        print(f"  全局规则: {p['stats']['global_chars']:,} 字符")
        print(f"  场景规则: {p['stats']['genre_chars']:,} 字符")
        ex_src_bytes = 0
        for m in p["examples_meta"]:
            ex_src_bytes += len(load_file(EXAMPLES / "football" / (m["theme"] + ".jsonl")))
        print(f"  few-shot: {p['stats']['n_examples']} 篇, {ex_src_bytes:,} 字节源")
        if p["examples_meta"]:
            print("入选范文:")
            for m in p["examples_meta"]:
                print(f"  - [{m['theme']}] {m['title']}  (#{m['content_sha256']})")
        if p["truncations"]:
            print("截断/跳过:")
            for name, lim in p["truncations"]:
                print(f"  - {name}: {lim}")
        if os.environ.get("VIET_DUMP_FULL") == "1":
            print("\n════════ 完整 system prompt ════════")
            print(p["system"])
        else:
            print("\n(设 VIET_DUMP_FULL=1 可打印完整 system prompt)")
        return

    from llm_client import LLMClient
    client = LLMClient(cfg)

    if args.interactive or not args.task:
        print("=== 越南语写作引擎 (nhập 'q' để thoát) ===")
        genre = args.genre
        while True:
            try:
                task = input("\n任务> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if task.lower() in ("q", "quit", "exit"):
                break
            if not task:
                continue
            print("\n--- 生成中 ---")
            print(write(client, task, genre, args.extra, args.format_contract, gen_kw))
            meta = getattr(write, "last_meta", {})
            if meta.get("truncated"):
                print(f"\n[警告] 输出可能被 max_tokens 截断(finish_reason=length)", file=sys.stderr)
        return

    out = write(client, args.task, args.genre, args.extra, args.format_contract, gen_kw)
    print(out)
    meta = getattr(write, "last_meta", {})
    if meta.get("truncated"):
        print("\n[警告] 输出可能被 max_tokens 截断(finish_reason=length)", file=sys.stderr)


if __name__ == "__main__":
    main()
