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


def parse_minute(m):
    """把分钟解析成可比较的数值。'45+2' -> 45.5(补时), 整数原样。"""
    if m is None:
        return None
    if isinstance(m, (int, float)):
        return float(m)
    s = str(m).strip()
    mm = re.match(r"^(\d+)\s*\+\s*(\d+)$", s)
    if mm:
        return int(mm.group(1)) + int(mm.group(2)) / 100.0
    try:
        return float(re.sub(r"[^0-9.]", "", s))
    except ValueError:
        return None


def parse_score(score):
    """把 [1,3] 或 {'home':1,'away':3} 统一成 (home, away)。"""
    if isinstance(score, list) and len(score) == 2:
        return int(score[0]), int(score[1])
    if isinstance(score, dict):
        return int(score.get("home", 0)), int(score.get("away", 0))
    raise ValueError(f"Không phân tích được tỷ số: {score!r}")


def compute(facts):
    """核心推算。返回 dict(见模块 docstring)。"""
    home = facts.get("home", "home")
    away = facts.get("away", "away")
    events = facts.get("events", [])
    # 按分钟排序(无分钟的放最后,保持相对顺序)
    goals = [e for e in events if e.get("type") in ("goal", "own_goal", "penalty")]
    goals_sorted = sorted([e for e in goals if e.get("minute") is not None],
                          key=lambda e: parse_minute(e["minute"]))
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
        # 判定动词——按**进球方视角**计算领先差(评审 v3 给的算法):
        #   lead_before = 进球方在进球前的净领先(正=领先, 负=落后, 0=平)
        #   lead_after  = lead_before + 1(这球必进)
        lead_before = (prev_h - prev_a) if ben == "home" else (prev_a - prev_h)
        lead_after = lead_before + 1
        if prev_h == 0 and prev_a == 0:
            verb = "mở tỷ số"                     # 全场首球
        elif lead_after == 0:
            verb = "gỡ hòa"                       # 进球后回到平局
        elif lead_before == 0:
            verb = "vượt lên dẫn"                 # 从平局取得领先(反超)
        elif lead_before < 0:
            verb = "rút ngắn cách biệt"           # 落后方追分,仍落后
        else:
            verb = "nâng tỷ số"                   # 领先方扩大(lead_before >= 1)
        player = e.get("player", "")
        # 乌龙球不计入射手统计(否则两个不同球员的乌龙会被算成同一人"梅开二度")
        if not own and player:
            scorer_count[player] = scorer_count.get(player, 0) + 1
        tag = verb
        if own:
            tag += " (phản lưới nhà)"
        # 可接受替代写法(不算错):领先从 1 球扩到 2 球时,"nhân đôi cách biệt" 可替 "nâng tỷ số"
        alts = []
        if verb == "nâng tỷ số" and lead_before == 1:
            alts.append("nhân đôi cách biệt")
        steps.append({
            "minute": e.get("minute"), "team": ben, "player": player,
            "score": f"{h}-{a}", "verb": tag, "accept_alt": alts,
            "own_goal": own,
            "detail": e.get("detail"),
            "assist": e.get("assist"),
            "var_checked": e.get("var_checked"),
        })

    # 纪律事件(红牌/第二黄):单独列出,按时间并入进程
    discipline = []
    for e in events:
        if e.get("type") in ("red", "second_yellow"):
            discipline.append({
                "minute": e.get("minute"),
                "team": e.get("team"),
                "player": e.get("player"),
                "kind": e.get("type"),
                "minute_known": e.get("minute") is not None,
            })

    # 决胜事件:胜方最后一次取得领先且此后未被追平的进球
    final_h, final_a = (parse_score(facts["final"]) if facts.get("final")
                        else (h, a))
    # 一致性:声明的 final 与事件推出的比分是否一致
    score_mismatch = bool(facts.get("final")) and (final_h, final_a) != (h, a)
    events_h, events_a = h, a          # 事件推出的比分(停用推导时用)
    winner = "home" if final_h > final_a else ("away" if final_a > final_h else None)
    # 点球大战(杯赛)
    pens = facts.get("penalties")
    pen_winner = None
    if isinstance(pens, (list, tuple)) and len(pens) == 2:
        try:
            if int(pens[0]) > int(pens[1]):
                pen_winner = "home"
            elif int(pens[1]) > int(pens[0]):
                pen_winner = "away"
        except (ValueError, TypeError):
            pen_winner = None
    decider = None
    if winner:
        # 决胜事件 = 胜方**最后一次从平局/落后转为领先**的进球(即最后一次"反超"),
        # 且此后未被追平。语义上这是"bàn quyết định"(越南语体育报道用法)。
        #   - 1-0/2-0 这类全程领先:从未落后 → 取**首开纪录**那球(它没被扳平)。
        #   - Thể Công 一役:60' 反超 2-1 是决胜球(16' 被扳平的球不算)。
        # 注意:64' 那种"锁定胜局"球(已领先后再进)不算决胜球。
        last_lead_idx = None
        for idx, s in enumerate(steps):
            ph, pa = map(int, s["score"].split("-"))
            w_leading = (ph > pa) if winner == "home" else (pa > ph)
            if not w_leading:
                continue
            # 此后是否被追平/反超
            later_eq = False
            for s2 in steps[idx + 1:]:
                p2h, p2a = map(int, s2["score"].split("-"))
                w2 = (p2h > p2a) if winner == "home" else (p2a > p2h)
                if not w2:
                    later_eq = True
                    break
            if later_eq:
                continue
            # 这是"未被追平的领先球"。看它是否为本段领先的**起点**
            # (即前一步胜方不领先或为 0-0) → 反超/首开纪录
            prev_lead = False
            if idx > 0:
                prh, pra = map(int, steps[idx - 1]["score"].split("-"))
                prev_lead = (prh > pra) if winner == "home" else (pra > prh)
            if not prev_lead:
                last_lead_idx = idx          # 保留最后一次"由不领先转为领先"
        if last_lead_idx is not None:
            s = steps[last_lead_idx]
            # 乌龙球:主角是"踢进乌龙的人",不是受益方球员;标题应聚焦受益方
            decider = {"minute": s["minute"], "player": s["player"],
                       "team": winner, "score": s["score"], "step_index": last_lead_idx,
                       "own_goal": bool(s.get("own_goal")),
                       "beneficiary": s.get("team")}
    comeback = False
    if winner:
        run_h = run_a = 0
        for s in steps:
            ph, pa = map(int, s["score"].split("-"))
            if (winner == "home" and pa > ph) or (winner == "away" and ph > pa):
                comeback = True

    # 冗余事实(可由事件推出的,标 derivable)
    derivable = []
    if steps and not score_mismatch:
        # 半场比分:上半场 = 分钟 <= 45 或补时(45+X,parse_minute 给 45.xx)
        def _in_first_half(mn):
            v = parse_minute(mn)
            return v is not None and v < 46      # 45+2 → 45.02 < 46 ✓
        first_half = [s for s in steps if _in_first_half(s["minute"])]
        # 若上半场段后紧跟无分钟事件,不强行判;只要有上半场进球就算
        if first_half and len(first_half) < len(steps):
            derivable.append({"fact": "tỷ số hiệp một", "value": first_half[-1]["score"],
                              "note": "có thể suy ra từ bàn thắng, không nên tách thành câu riêng"})
    # 胜负推导仅在 final 与事件一致时给出(不一致说明输入有误)
    if winner and not score_mismatch:
        derivable.append({"fact": "giành trọn 3 điểm",
                          "note": "có thể suy ra từ đội thắng, không nên làm câu kết"})

    # 缺项
    absent = []
    if not facts.get("round"):
        absent.append("vòng đấu")
    if not facts.get("venue"):
        absent.append("sân")
    # 红牌/第二黄的分钟
    for e in events:
        if e.get("type") == "second_yellow" and e.get("minute") is None:
            absent.append("phút thẻ vàng thứ hai")
        elif e.get("type") == "red" and e.get("minute") is None:
            absent.append("phút thẻ đỏ")

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
    # 少打一人(用实际队名)
    for e in events:
        if e.get("type") in ("red", "second_yellow"):
            tn = home if e.get("team") == "home" else away
            title_candidates.append(f"{tn} chơi thiếu người")

    return {
        "score_progression": steps,
        "discipline": discipline,
        "decider": decider,
        "comeback": comeback,
        "derivable": derivable,
        "absent": absent,
        "title_candidates": title_candidates,
        "final": f"{final_h}-{final_a}",
        "score_mismatch": score_mismatch,
        "events_score": f"{events_h}-{events_a}",
        "penalty_winner": pen_winner,
        "home_name": home,
        "away_name": away,
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
                          "msg": f"Cụm mô tả mơ hồ/nội bộ '{v}', nên bỏ hoặc thay bằng thông tin cụ thể"})
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
                    "msg": f"Với tỷ số {key} phải dùng '{correct}', nhưng đầu vào dùng '{used[0]}'"})
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
    hn = result.get("home_name", "đội nhà")
    an = result.get("away_name", "đội khách")

    def _side(s):
        return hn if s == "home" else an

    lines = ["## Dữ kiện đã chuẩn hoá (dùng đúng các mục này):"]
    if result.get("score_mismatch"):
        lines.append(f"- ⚠ Tỷ số công bố ({result['final']}) KHÔNG khớp với diễn biến "
                     f"suy ra từ bàn thắng ({result['events_score']}). "
                     f"Kiểm tra lại dữ kiện trước khi viết; KHÔNG dùng các suy luận "
                     f"về thắng/thua/bảng xếp hạng.")
    d = result.get("decider")
    if d:
        if d.get("own_goal"):
            lines.append(f"- Bàn quyết định: phút {d['minute']}, phản lưới nhà của "
                         f"{d['player']} → có lợi cho {_side(d.get('beneficiary'))}. "
                         f"Tiêu đề nên tập trung vào đội hưởng lợi, không lấy tên người đá phản làm nhân vật chính.")
        else:
            mn = f"phút {d['minute']}" if d["minute"] is not None else "(không rõ phút)"
            lines.append(f"- Bàn quyết định: {mn}, {d['player']} "
                         f"({d['score']}) → dùng cho tiêu đề")
    if result["comeback"]:
        lines.append("- Đây là màn ngược dòng")
    if result.get("penalty_winner"):
        lines.append(f"- Loạt luân lưu: {_side(result['penalty_winner'])} thắng "
                     f"(dùng khi viết về trận đấu cúp)")
    lines.append("- Diễn biến (dùng đúng động từ, theo trình tự thời gian):")
    # 把纪律事件与进球按时间合并排序
    timeline = []
    for s in result["score_progression"]:
        timeline.append((parse_minute(s["minute"]), "goal", s))
    for e in result.get("discipline", []):
        timeline.append((parse_minute(e["minute"]), "disc", e))
    timeline.sort(key=lambda x: (x[0] is None, x[0] if x[0] is not None else 0))
    for _, kind, s in timeline:
        if kind == "goal":
            mn = f"phút {s['minute']}" if s["minute"] is not None else "(không rõ phút)"
            extra = f", kiến tạo {s['assist']}" if s.get("assist") else ""
            var = " (VAR công nhận)" if s.get("var_checked") else ""
            lines.append(f"    {mn}: {s['player']} → **{s['verb']}** {s['score']}{extra}{var}")
        else:
            mn = f"phút {s['minute']}" if s["minute"] is not None else "(không rõ phút)"
            label = "thẻ vàng thứ hai (bị truất quyền)" if s["kind"] == "second_yellow" else "thẻ đỏ"
            lines.append(f"    {mn}: {s['player']} ({_side(s['team'])}) → **{label}**")
    if result.get("title_candidates"):
        lines.append("- Gợi ý cho tiêu đề: " + " / ".join(result["title_candidates"]))
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
