#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_style.py — 越南语新闻稿风格检查器。

输入:稿件(文本文件或 --text) + 可选 facts.json(用于比分/决胜事件相关规则)。
输出:疑点清单(不自动判决)。每条命中给出规则号、片段、说明。

规则(对应第三轮评审 S1-S9):
  S1 比分动词矛盾   — 动词与推算进程不一致(需 facts)
  S2 重复比分       — 同一比分单独成句 >1 次
  S3 先预告再展开   — 无分钟的事件句后紧跟含分钟的同类事件句
  S4 结尾复述       — 末段只含最终比分/giành trọn 3 điểm 等,无新信息
  S5 内部/模糊描述  — vòng mới nhất、theo dữ liệu được cung cấp、đề bài 等
  S6 纪律术语       — "nhận 2 thẻ vàng" → 建议 "nhận thẻ vàng thứ hai"
  S7 情绪词密度     — 新闻体裁中情绪词每千字超阈值
  S8 待审搭配       — 编辑观察表(quyết định cục diện 等),只提示
  S9 标题决胜事件   — 标题主角不含决胜事件球员,或把被扳平进球当决胜(需 facts)

用法:
    python bin/check_style.py --text-file draft.txt
    python bin/check_style.py --text-file draft.txt --facts facts.json
    python bin/check_style.py --text-file draft.txt --facts facts.json --json
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))

# --- 词表 ---
VAGUE = ["vòng mới nhất", "vòng gần nhất", "mới đây", "gần đây nhất",
         "theo dữ liệu được cung cấp", "đề bài", "theo thông tin được cung cấp"]
EMOTION = ["rực lửa", "nghẹt thở", "vỡ oà", "vỡ òa", "thăng hoa", "cơn mưa bàn thắng",
           "bùng nổ", "nóng bỏng", "kịch tính", "nghẹt thở", "đỉnh cao"]
# S8 编辑观察表(只提示,不判错)
WATCH = ["quyết định cục diện", "mạch trận", "tâm điểm", "định đoạt trận đấu"]
DISCIPLINE_BAD = [r"nhận\s+2\s+thẻ\s+vàng", r"2\s+thẻ\s+vàng",
                  r"nhận\s+hai\s+thẻ\s+vàng"]
DISCIPLINE_SUGGEST = "nhận thẻ vàng thứ hai"

# 可推导事实(结尾复述用)
RESTATE = ["giành trọn 3 điểm", "ra về với 3 điểm", "giành trọn ba điểm",
           "có được 3 điểm"]
# 事件动词(先预告再展开用)
PREVIEW_VERBS = ["có bàn gỡ", "có bàn thắng", "lên tiếng", "ghi bàn", "có bàn rút ngắn"]
# 情绪词
GOAL_VERBS = ["mở tỷ số", "gỡ hòa", "san bằng", "vượt lên dẫn", "nâng tỷ số",
              "nhân đôi cách biệt", "rút ngắn cách biệt"]


def split_sentences(text):
    """按 .!?… 和换行切句;返回句子列表(去空)。"""
    raw = re.split(r"(?<=[.!?…])\s+|\n+", text)
    return [s.strip() for s in raw if s.strip()]


def _has_minute(s):
    return bool(re.search(r"phút\s+\d+", s, re.I))


def _scores_in(s):
    """返回句中的比分(保持书写顺序的两种解释都给出)。"""
    out = []
    for m in re.finditer(r"(\d)\s*[-–]\s*(\d)", s):
        out.append((int(m.group(1)), int(m.group(2))))
    return out


def check(task_text, facts=None):
    """返回疑点列表。每条: {rule, snippet, msg}。

    忽略以 # 或 > 开头的元信息行(来自回归样本的注释/引言),避免被当成标题。
    """
    task_text = "\n".join(l for l in task_text.split("\n")
                          if not l.lstrip().startswith(("#", ">")))
    issues = []
    sents = split_sentences(task_text)
    lines = [l for l in task_text.split("\n") if l.strip()]
    title = lines[0] if lines else ""

    # ---- S1 比分动词矛盾(需 facts) ----
    if facts:
        try:
            from prepare_facts import compute
            result = compute(facts)
            correct_map = {s["score"]: s["verb"] for s in result["score_progression"]}
            # 可接受替代(如 1-3 处 nhân đôi cách biệt 可替 nâng tỷ số)
            alt_map = {s["score"]: set(s.get("accept_alt") or [])
                       for s in result["score_progression"]}
            VERBS = ["nâng tỷ số", "nhân đôi cách biệt", "vượt lên dẫn", "gỡ hòa",
                     "mở tỷ số", "rút ngắn cách biệt"]
            for m in re.finditer(r"(\d)\s*[-–]\s*(\d)", task_text):
                h, a = int(m.group(1)), int(m.group(2))
                # 比分可能写成主队在前或进球方在前,两种顺序都查
                matched = None
                for key in (f"{h}-{a}", f"{a}-{h}"):
                    if key in correct_map:
                        matched = key
                        break
                if matched:
                    key = matched
                    correct = correct_map[key]
                    accepted = {correct} | alt_map.get(key, set())
                    # 在比分前 32 字符内找动词("...nhân đôi cách biệt lên 3-0" 中动词离比分较远)
                    near = task_text[max(0, m.start() - 32):m.start()].lower()
                    used = [v for v in VERBS if v in near]
                    # 排除"vượt lên dẫn trước"(短语,非标签)
                    if "vượt lên dẫn trước" in near:
                        used = [v for v in used if v != "vượt lên dẫn"]
                    if used and not (set(used) & accepted):
                        alts = alt_map.get(key, set())
                        alt_txt = f"(或可接受替代: {', '.join(alts)})" if alts else ""
                        issues.append({"rule": "S1", "snippet": f"{used[0]} ... {key}",
                                       "msg": f"比分 {key} 应用 '{correct}'{alt_txt},"
                                              f"用了 '{used[0]}'"})
        except Exception as e:
            issues.append({"rule": "S1", "snippet": "-", "msg": f"facts 处理失败: {e}"})

    # ---- S2 重复比分 ----
    # 规则:同一比分在**相邻两句**里重复出现,且后句是"单独陈述比分"的短句。
    # 导语与正文各一次不算(评审明确)。跨段落也不算。
    for idx in range(1, len(sents)):
        cur = sents[idx]
        if len(cur) > 60:
            continue
        cur_sc = {f"{h}-{a}" for h, a in _scores_in(cur)}
        # 看前 2 句(比分往往在上一句或上上一句已出现)
        prev_sc = set()
        for back in (1, 2):
            if idx - back < 0:
                break
            for h, a in _scores_in(sents[idx - back]):
                prev_sc |= {f"{h}-{a}", f"{a}-{h}"}
        dup = {s for s in cur_sc if s in prev_sc}
        for key in dup:
            issues.append({"rule": "S2", "snippet": cur[:50],
                           "msg": f"比分 {key} 在上一句已出现,此句单独复述(重复)"})

    # ---- S3 先预告再展开 ----
    # 前句:无分钟、且是"预告式"事件句(有进球/事件动词但无细节)
    # 后句:含分钟的同场事件句 → 重复
    EVENT_WORDS = ["ghi bàn", "dứt điểm", "sút", "đánh đầu", "gỡ hòa", "rút ngắn",
                   "nâng tỷ số", "mở tỷ số", "thẻ", "rời sân", "vào sân"]
    for i in range(len(sents) - 1):
        cur, nxt = sents[i], sents[i + 1]
        if _has_minute(cur):
            continue
        if not any(v in cur.lower() for v in PREVIEW_VERBS):
            continue
        # 前句短、像预告(不含具体球员细节词也可),后句含分钟且是事件句
        if _has_minute(nxt) and any(w in nxt.lower() for w in EVENT_WORDS):
            issues.append({"rule": "S3", "snippet": cur[:50],
                           "msg": "先预告再展开同一事件(前句无分钟预告,后句展开细节)"})

    # ---- S4 结尾复述 ----
    if sents:
        last = sents[-1]
        # 末段只含复述,无新实体/数字
        has_restate = any(r in last.lower() for r in RESTATE)
        # 简单判断"无新信息":长度短且含比分或复述词
        if has_restate or (len(last) < 80 and _scores_in(last) and _has_minute(last) is False):
            # 排除末句是新事实(含新球员名/新事件)
            fresh = bool(re.search(r"(thay|vào sân|chấn thương|tuyên bố|phát biểu)", last, re.I))
            if not fresh:
                issues.append({"rule": "S4", "snippet": last[:60],
                               "msg": "结尾复述赛果/积分,无新信息(建议删或改为体系后果)"})

    # ---- S5 内部/模糊描述 ----
    for v in VAGUE:
        if v in task_text.lower():
            issues.append({"rule": "S5", "snippet": v,
                           "msg": f"内部/模糊描述 '{v}',应省略或替换为具体信息"})

    # ---- S6 纪律术语 ----
    for pat in DISCIPLINE_BAD:
        for m in re.finditer(pat, task_text, re.I):
            issues.append({"rule": "S6", "snippet": m.group(0),
                           "msg": f"建议改为 '{DISCIPLINE_SUGGEST}'"})

    # ---- S7 情绪词密度 ----
    n = len(task_text)
    hit = [w for w in EMOTION if w in task_text.lower()]
    if n > 0:
        per_k = len(hit) / (n / 1000.0)
        if per_k > 3:      # 每千字超 3 个情绪词
            issues.append({"rule": "S7", "snippet": ", ".join(hit[:5]),
                           "msg": f"情绪词密度偏高({len(hit)} 个 / {n} 字),新闻应偏中性"})

    # ---- S8 待审搭配 ----
    for w in WATCH:
        if w in task_text.lower():
            issues.append({"rule": "S8", "snippet": w,
                           "msg": f"待审搭配 '{w}',请编辑确认"})

    # ---- S9 标题决胜事件(需 facts) ----
    if facts:
        try:
            from prepare_facts import compute
            result = compute(facts)
            d = result.get("decider")
            if d and title:
                # 标题应含决胜球员名
                pl = d["player"] or ""
                parts = [x for x in pl.split() if len(x) > 2]
                if parts and not any(x in title for x in parts):
                    issues.append({"rule": "S9", "snippet": title[:50],
                                   "msg": f"标题未含决胜事件球员 '{pl}'"})
                # 反向:标题把"非决胜的进球者"也列为主角(与决胜球员并列)
                dec_parts = set(parts)
                for s in result["score_progression"]:
                    if s["player"] == pl:
                        continue        # 跳过决胜球员本身
                    s_parts = [x for x in s["player"].split() if len(x) > 3]
                    if not s_parts:
                        continue
                    if any(x in title for x in s_parts) and (not parts or
                            any(x in title for x in parts)):
                        # 标题同时含非决胜球员和决胜球员 → 并列嫌疑
                        if any(x in title for x in parts):
                            issues.append({
                                "rule": "S9", "snippet": title[:50],
                                "msg": f"标题把非决胜球员 '{s['player']}'(其进球已被扳平/非决定性)"
                                       f"与决胜球员并列,建议只突出决胜球员"})
                            break
        except Exception:
            pass

    return issues


def main():
    ap = argparse.ArgumentParser(description="越南语新闻稿风格检查")
    ap.add_argument("--text-file")
    ap.add_argument("--text")
    ap.add_argument("--facts", help="facts.json(用于 S1/S9)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    text = args.text
    if args.text_file and not text:
        text = Path(args.text_file).read_text(encoding="utf-8")
    if not text:
        ap.error("需要 --text 或 --text-file")
    facts = None
    if args.facts:
        facts = json.loads(Path(args.facts).read_text(encoding="utf-8"))

    issues = check(text, facts)
    if args.json:
        print(json.dumps(issues, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}\n风格检查: {len(issues)} 个疑点\n{'='*60}")
        if not issues:
            print("→ 无命中。")
        for it in issues:
            print(f"  [{it['rule']}] {it['msg']}")
            print(f"        \"{it['snippet']}\"")
        print(f"\n※ 这些是提示,不是判决。由编辑最终确认。")


if __name__ == "__main__":
    main()
