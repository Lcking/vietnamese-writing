#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prepare_facts.py — 事实预处理(纯函数,不调用模型)。

输入:赛果报道的结构化事实 JSON。
输出:给模型的确定性命中——比分动词标签、决胜事件、冗余事实、缺项、输入纠错。

为什么需要:模型(尤其本地小模型)会把"1-1 后反超"写成"nâng tỷ số"(应为"vượt lên dẫn"),
会把被扳平的进球当"决胜球"。这些是**可确定性推算**的,不该交给模型猜。

用法:
    python bin/prepare_facts.py --facts facts.json
    python bin/prepare_facts.py --facts facts.json --json   # 机器可读输出
"""
import argparse
import json
import re
import sys


def parse_score(score):
    """把 [1,3] 或 {'home':1,'away':3} 统一成 (home, away)。"""
    if isinstance(score, list) and len(score) == 2:
        return int(score[0]), int(score[1])
    if isinstance(score, dict):
        return int(score.get("home", 0)), int(score.get("away", 0))
    raise ValueError(f"无法解析比分: {score!r}")


def compute(facts):
    """核心推算。返回 dict(见模块 docstring)。"""
    home = facts.get("home", "home")
    away = facts.get("away", "away")
    events = facts.get("events", [])
    # 按分钟排序(无分钟的放最后,保持相对顺序)
    goals = [e for e in events if e.get("type") in ("goal", "own_goal", "penalty")]
    goals_sorted = sorted([e for e in goals if e.get("minute") is not None],
                          key=lambda e: e["minute"])
    goals_nom = [e for e in goals if e.get("minute") is None]
    goals_ordered = goals_sorted + goals_nom

    # 逐球推算比分状态与动词
    h = a = 0
    steps = []
    scorer_count = {}
    for e in goals_ordered:
        team = e.get("team")            # "home"/"away"
        own = e.get("type") == "own_goal"
        # 乌龙球记入受益方
        ben = team
        if own:
            ben = "away" if team == "home" else "home"
        prev_h, prev_a = h, a
        if ben == "home":
            h += 1
        else:
            a += 1
        # 判定动词(按最终比分状态,从具体到一般)
        prev_diff = prev_h - prev_a     # 正=主队领先
        now_diff = h - a
        if prev_h == 0 and prev_a == 0:
            verb = "mở tỷ số"
        elif h == a and prev_h != prev_a:
            verb = "gỡ hòa"
        elif (prev_diff <= 0 and now_diff > 0) or (prev_diff >= 0 and now_diff < 0):
            # 从平/落后 → 领先(=反超),或从领先→落后
            verb = "vượt lên dẫn"
        else:
            # 同一方继续领先(prev 和 now 都同号),或落后方缩小差距
            same_side_lead = (prev_diff > 0 and now_diff > 0) or (prev_diff < 0 and now_diff < 0)
            if same_side_lead:
                # 领先方继续进球 → 主标签 "nâng tỷ số"。
                # "nhân đôi cách biệt" 仅在领先从 1 球扩大到 2 球(prev=1, now=2)时
                # 作为**可接受替代**(不是必须)。两者都不算错。
                verb = "nâng tỷ số"
            else:
                verb = "rút ngắn cách biệt"
        player = e.get("player", "")
        scorer_count[player] = scorer_count.get(player, 0) + 1
        tag = verb
        if own:
            tag += " (phản lưới nhà)"
        # 可接受替代写法(不算错):领先从 1 球扩到 2 球时,"nhân đôi cách biệt" 可替 "nâng tỷ số"
        alts = []
        if verb == "nâng tỷ số" and (
                abs(prev_diff) == 1 and abs(now_diff) == 2 and
                ((prev_diff > 0 and now_diff > 0) or (prev_diff < 0 and now_diff < 0))):
            alts.append("nhân đôi cách biệt")
        steps.append({
            "minute": e.get("minute"), "team": ben, "player": player,
            "score": f"{h}-{a}", "verb": tag, "accept_alt": alts,
            "detail": e.get("detail"),
            "assist": e.get("assist"),
            "var_checked": e.get("var_checked"),
        })

    # 决胜事件:胜方最后一次取得领先且此后未被追平的进球
    final_h, final_a = (parse_score(facts["final"]) if facts.get("final")
                        else (h, a))
    winner = "home" if final_h > final_a else ("away" if final_a > final_h else None)
    decider = None
    if winner:
        # 决胜事件 = 胜方**从平局或落后转为领先**的那球(不把 0-0 开纪录算作决胜)。
        # 遍历,记录"胜方由(平/落后)变为领先"的那次转换。
        prev_h = prev_a = None
        for idx, s in enumerate(steps):
            ph, pa = map(int, s["score"].split("-"))
            if prev_h is not None:
                prev_leading = (prev_h > prev_a) if winner == "home" else (prev_a > prev_h)
                now_leading = (ph > pa) if winner == "home" else (pa > ph)
                # 前提:转换前不是 0-0 开纪录(即之前已有过进球)
                was_opening = (prev_h == 0 and prev_a == 0)
                if now_leading and not prev_leading and not was_opening:
                    decider = {"minute": s["minute"], "player": s["player"],
                               "team": winner, "score": s["score"], "step_index": idx}
                    break
            prev_h, prev_a = ph, pa
        # decider 实际是最后一个使胜方领先的球,但需确认此后未被追平(即最终仍领先)
        # 已由 winner 判定保证;若胜方曾落后,标注 ngược dòng
    comeback = False
    if winner:
        run_h = run_a = 0
        for s in steps:
            ph, pa = map(int, s["score"].split("-"))
            if (winner == "home" and pa > ph) or (winner == "away" and ph > pa):
                comeback = True

    # 冗余事实(可由事件推出的,标 derivable)
    derivable = []
    if steps:
        # 半场比分
        first_half = [s for s in steps if s["minute"] is not None and s["minute"] <= 45]
        if first_half:
            derivable.append({"fact": "tỷ số hiệp một", "value": first_half[-1]["score"],
                              "note": "可由进球推算,勿单独成句"})
    if winner:
        derivable.append({"fact": "giành trọn 3 điểm",
                          "note": "可由胜方推算,勿作结尾总结"})

    # 缺项
    absent = []
    for k in ("round", "venue"):
        if not facts.get(k):
            absent.append(k)
    # 红牌/第二黄的分钟
    for e in events:
        if e.get("type") in ("red", "second_yellow") and e.get("minute") is None:
            absent.append(f"{e.get('type')}_minute")

    # 第二名/第三名球员(标题候选)
    title_candidates = []
    if decider:
        title_candidates.append(f"{decider['player']} (bàn quyết định)")
    for pname, cnt in scorer_count.items():
        if cnt >= 2:
            label = "lập cú đúp" if cnt == 2 else "hat-trick"
            title_candidates.append(f"{pname} ({label})")
    if comeback:
        title_candidates.append("(ngược dòng)")
    # 少打一人
    for e in events:
        if e.get("type") in ("red", "second_yellow"):
            title_candidates.append(f"{e.get('team')} chơi thiếu người")

    return {
        "score_progression": steps,
        "decider": decider,
        "comeback": comeback,
        "derivable": derivable,
        "absent": absent,
        "title_candidates": title_candidates,
        "final": f"{final_h}-{final_a}",
    }


# ---- 自由文本纠错(检测输入里与推算矛盾的动词/模糊描述) ----
VAGUE = ["vòng mới nhất", "mới đây", "gần đây nhất", "theo dữ liệu được cung cấp",
         "đề bài", "vòng gần nhất"]


def check_input_text(raw_text, result):
    """检测自由文本输入里的问题。返回警告列表。"""
    warns = []
    low = raw_text.lower()
    for v in VAGUE:
        if v in low:
            warns.append({"kind": "vague", "text": v,
                          "msg": f"描述模糊/内部用语 '{v}',应省略或替换为具体信息"})
    # 比分动词矛盾:输入里的(动词, 比分)对是否与推算矛盾。
    # 推算得到 {比分: 正确动词},输入里若在比分旁用了别的动词 → 警告。
    correct_map = {s["score"]: s["verb"] for s in result["score_progression"]}
    VERBS = ["nâng tỷ số", "nhân đôi cách biệt", "vượt lên dẫn", "gỡ hòa",
             "mở tỷ số", "rút ngắn cách biệt"]
    for m in re.finditer(r"(\d)\s*[-–]\s*(\d)", raw_text):
        h, a = int(m.group(1)), int(m.group(2))
        # 两种主客顺序都匹配推算比分
        for key in (f"{h}-{a}", f"{a}-{h}"):
            if key not in correct_map:
                continue
            correct = correct_map[key]
            ctx = raw_text[max(0, m.start() - 35):m.end()]
            used = [v for v in VERBS if v in ctx.lower()]
            if used and correct not in used:
                warns.append({
                    "kind": "verb_conflict",
                    "text": f"{used[0]} ... {key}",
                    "msg": f"比分为 {key} 时应用 '{correct}',输入用了 '{used[0]}'"})
            break
    # 去重
    seen = set()
    uniq = []
    for w in warns:
        k = (w["kind"], w["text"])
        if k not in seen:
            seen.add(k)
            uniq.append(w)
    return uniq


def format_for_prompt(result, warns):
    """把预处理结果格式化成注入用户提示的文本。"""
    lines = ["## Dữ kiện đã chuẩn hoá (dùng đúng các mục này):"]
    if result["decider"]:
        d = result["decider"]
        lines.append(f"- Bàn quyết định: phút {d['minute']}, {d['player']} "
                     f"({d['score']}) → dùng cho tiêu đề")
    if result["comeback"]:
        lines.append("- Đây là màn ngược dòng")
    lines.append("- Diễn biến (dùng đúng động từ):")
    for s in result["score_progression"]:
        mn = f"phút {s['minute']}" if s["minute"] else "(không rõ phút)"
        extra = f", kiến tạo {s['assist']}" if s.get("assist") else ""
        var = " (VAR công nhận)" if s.get("var_checked") else ""
        lines.append(f"    {mn}: {s['player']} → **{s['verb']}** {s['score']}{extra}{var}")
    if result["derivable"]:
        lines.append("- KHÔNG viết riêng (đã suy ra được): " +
                     ", ".join(d["fact"] for d in result["derivable"]))
    if result["absent"]:
        lines.append("- Thiếu dữ kiện (bỏ qua, không thay bằng cụm mơ hồ): " +
                     ", ".join(result["absent"]))
    if warns:
        lines.append("- ⚠ Cảnh báo từ dữ kiện gốc:")
        for w in warns:
            lines.append(f"    • {w['msg']}")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--facts", required=True)
    ap.add_argument("--text", default=None, help="原始自由文本(用于纠错)")
    ap.add_argument("--json", action="store_true", help="输出机器可读 JSON")
    args = ap.parse_args()

    facts = json.loads(open(args.facts, encoding="utf-8").read())
    result = compute(facts)
    warns = check_input_text(args.text, result) if args.text else []

    if args.json:
        print(json.dumps({"computed": result, "warnings": warns},
                         ensure_ascii=False, indent=2))
    else:
        print(format_for_prompt(result, warns))


if __name__ == "__main__":
    main()
