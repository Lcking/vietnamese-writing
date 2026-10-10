#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
viet_writer — 越南语写作引擎主入口
用法:
    python bin/viet_writer.py --task "viết bản tin MU thắng 3-1" --genre football_tin_tuc
    python bin/viet_writer.py --task "bình luận trận Việt Nam - Thái Lan"   # 自动识别足球
    python bin/viet_writer.py --interactive
"""
import os, sys, argparse, json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
from llm_client import LLMClient

REFERENCES = ROOT / "references"
EXAMPLES = ROOT / "examples"
PROMPTS = ROOT / "prompts"

GENRES = ["van_hoc", "bao_chi", "bach_khoa", "cong_van",
          "mang_xa_hoi", "doi_song", "chuyen_mon",
          "football_thuat_ngu", "football_binh_luan", "football_tin_tuc",
          "football_chuyen_nhuong", "football_doi_tuyen", "football_nhan_vat"]

# 自动识别足球任务的触发词
FOOTBALL_HINTS = ["bóng đá", "bình luận", "trận đấu", "cầu thủ", "đội bóng",
                  "world cup", "champions league", "v-league", "aff cup",
                  "chuyển nhượng", "bàn thắng", "hlv", "huấn luyện viên",
                  "tuyển việt nam", "sea games", "ghi bàn", "thủ môn",
                  "足球", "解说", "比赛", "球队", "世界杯", "转会"]

def load_file(p):
    try:
        return Path(p).read_text(encoding="utf-8")
    except Exception:
        return ""

def pick_examples(genre, n=4):
    """为足球 genre 注入 few-shot 范文"""
    theme_map = {
        "football_binh_luan": ["doi_tuyen_vn", "world_cup", "phan_tich_chien_thuat"],
        "football_tin_tuc": ["world_cup", "ngoai_hang", "champions_league"],
        "football_chuyen_nhuong": ["chuyen_nhuong"],
        "football_doi_tuyen": ["doi_tuyen_vn", "chau_a"],
        "football_nhan_vat": ["ngoai_hang", "world_cup", "doi_tuyen_vn"],
        "football_thuat_ngu": ["phan_tich_chien_thuat"],
    }
    dirs = theme_map.get(genre, [])
    out = []
    for d in dirs:
        fp = EXAMPLES / "football" / f"{d}.jsonl"
        if not fp.exists():
            continue
        lines = fp.read_text(encoding="utf-8").splitlines()
        for line in lines[:2]:
            try:
                r = json.loads(line)
                out.append(f"[{r['title']}]\n{r['content'][:1200]}")
            except Exception:
                pass
        if len(out) >= n:
            break
    return out

def build_system_prompt(genre=None):
    """组装系统提示:核心规则 + 全局维度 + 文体规范 + few-shot 范文"""
    parts = [load_file(PROMPTS / "system_vi_writer.md")]
    for f in sorted(REFERENCES.glob("_global_*.md")):
        parts.append(load_file(f))
    if genre and genre in GENRES:
        parts.append(load_file(REFERENCES / f"{genre}.md"))
        # 足球类注入范文
        if genre.startswith("football_"):
            ex = pick_examples(genre)
            if ex:
                parts.append("## Ví dụ mẫu (bài thật từ báo bóng đá Việt Nam)\n\n" +
                             "\n\n---\n\n".join(ex))
    elif genre is None:
        # 无指定:加载所有文体规范
        for g in GENRES:
            fp = REFERENCES / f"{g}.md"
            if fp.exists():
                parts.append(load_file(fp))
    return "\n\n---\n\n".join(p for p in parts if p.strip())

def detect_genre(task):
    """从任务描述自动识别足球 genre"""
    t = task.lower()
    if not any(h in t for h in FOOTBALL_HINTS):
        return None
    if any(k in t for k in ["chuyển nhượng", "转会"]): return "football_chuyen_nhuong"
    if any(k in t for k in ["bản tin", "新闻", "kết quả", "tỷ số"]): return "football_tin_tuc"
    if any(k in t for k in ["chân dung", "tiểu sử", "人物", "cầu thủ", "hlv"]): return "football_nhan_vat"
    if any(k in t for k in ["tuyển việt nam", "đội tuyển", "aff cup", "sea games"]): return "football_doi_tuyen"
    if any(k in t for k in ["thuật ngữ", "术语"]): return "football_thuat_ngu"
    return "football_binh_luan"  # 默认足球=解说

def write(client, task, genre=None, extra=""):
    if genre is None:
        genre = detect_genre(task)
    system = build_system_prompt(genre)
    user = f"""Yêu cầu viết:
{task}

{f"Nhóm văn bản: {genre}" if genre else ""}
{extra}

Hãy viết bằng tiếng Việt, đảm bảo tự nhiên, đúng phong cách, phù hợp với người đọc Việt Nam.
Chỉ trả về NỘI DUNG BÀI VIẾT, không giải thích."""
    return client.chat(system, user, max_tokens=4000, temperature=0.8)

def main():
    ap = argparse.ArgumentParser(description="越南语写作引擎")
    ap.add_argument("--task", "-t", help="写作任务(越南语或中文)")
    ap.add_argument("--genre", "-g", choices=GENRES, help="文体类型(不填则自动识别)")
    ap.add_argument("--extra", "-e", default="", help="额外要求")
    ap.add_argument("--config", "-c", help="配置文件路径(JSON/YAML)")
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
            print(write(client, task, genre, args.extra))
        return

    print(write(client, args.task, args.genre, args.extra))

if __name__ == "__main__":
    main()
