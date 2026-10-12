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


def base_minute(m):
    """返回加号前的**基础**分钟(用于判定加时)。'90+4' → 90, '120+2' → 120。"""
    if m is None:
        return None
    if isinstance(m, (int, float)):
        return float(m)
    s = str(m).strip()
    mm = re.match(r"^(\d+)", s)
    if mm:
        return float(mm.group(1))
    return parse_minute(m)


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

    # 修6/1: team 字段允许直接写队名 → 归一化成 home/away
    # 比较前做 NFC + 大小写折叠(保留声调符号,不做去声调)
    import unicodedata as _ud
    def _fold(x):
        return _ud.normalize("NFC", str(x).strip()).casefold()
    team_err = []
    _fh, _fa = _fold(home), _fold(away)

    def _norm_team(v):
        if v in ("home", "away"):
            return v
        if v is None:
            return None
        s = _fold(v)
        if s == _fh:
            return "home"
        if s == _fa:
            return "away"
        team_err.append(str(v))
        return None

    valid_events = []
    for _e in events:
        raw_team = _e.get("team")
        nt = _norm_team(raw_team)
        if nt is None and raw_team is not None:
            # 映射不上:该事件**不参与**比分计算,只单独报一条警告
            continue
        _e["team"] = nt
        valid_events.append(_e)
    events = valid_events
    # 按分钟排序(无分钟的放最后,保持相对顺序)
    goals = [e for e in events if e.get("type") in ("goal", "own_goal", "penalty")]
    goals_sorted = sorted([e for e in goals if e.get("minute") is not None],
                          key=lambda e: parse_minute(e["minute"]))
    goals_nom = [e for e in goals if e.get("minute") is None]
    goals_ordered = goals_sorted + goals_nom
    # 修5: 只要有关键进球缺分钟,顺序不可靠 → 停用顺序依赖的推算
    # 顺序可靠性只取决于**有效进球**是否都有分钟(被排除的无效事件不算)
    order_reliable = (len(goals_nom) == 0)

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
        if not order_reliable:
            verb = "?"                            # 顺序不可靠 → 不给动词
        elif prev_h == 0 and prev_a == 0:
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
            "penalty": (e.get("type") == "penalty"),
            "detail": e.get("detail"),
            "assist": e.get("assist"),
            "var_checked": e.get("var_checked"),
        })

    # 罚丢点球(不改变比分,但要告知写稿人)
    missed_pens = []
    for e in events:
        if e.get("type") == "missed_penalty":
            missed_pens.append({"minute": e.get("minute"), "team": e.get("team"),
                                "player": e.get("player")})

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
    final_provided = bool(facts.get("final"))
    final_h, final_a = (parse_score(facts["final"]) if final_provided else (h, a))
    # 一致性:声明的 final 与事件推出的比分是否一致
    score_mismatch = final_provided and (final_h, final_a) != (h, a)
    events_h, events_a = h, a          # 事件推出的比分(停用推导时用)
    # 胜负仅在最终比分可靠时推导(未提供 final 或顺序不可靠 → 不推)
    # 注:final 与事件一致是正常情况,此时同样要推(此处曾误写成 != 才推)
    # 胜负只需最终比分可靠即可推(不依赖进球顺序);逆转/决胜球才依赖顺序
    winner = None
    if final_provided and not score_mismatch and final_h != final_a:
        winner = "home" if final_h > final_a else "away"
    # 3) 赛事类型:cup 无积分;加时/点球本身也说明是淘汰赛
    comp_type = str(facts.get("competition_type") or "").strip().lower()

    # 点球大战(杯赛)
    pens = facts.get("penalties")
    pen_winner = None
    pen_warn = None
    if isinstance(pens, (list, tuple)) and len(pens) == 2:
        try:
            p0, p1 = int(pens[0]), int(pens[1])
            if p0 == p1:
                # 点球不可能打平(会一直踢到分胜负) → 忽略
                pen_warn = "tỷ số luân lưu không hợp lệ (hòa)"
                pens = None
            elif final_h != final_a:
                # 常规时间已分胜负 → 点球数据矛盾,忽略
                pen_warn = ("có loạt luân lưu nhưng tỷ số chung cuộc đã phân định "
                            "thắng thua → bỏ qua dữ kiện luân lưu")
                pens = None
            else:
                pen_winner = "home" if p0 > p1 else "away"
        except (ValueError, TypeError):
            pen_warn = "tỷ số luân lưu không hợp lệ"
            pens = None
    has_extra_time = any(
        (base_minute(e.get("minute")) is not None and 91 <= base_minute(e.get("minute")) <= 120)
        for e in events)
    is_knockout = (comp_type == "cup") or (pen_winner is not None) or has_extra_time
    decider = None
    if winner and order_reliable:
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
    if winner and not score_mismatch:
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
    # "3 分"只适用于联赛;杯赛淘汰赛没有积分
    if winner and not score_mismatch and not is_knockout:
        derivable.append({"fact": "giành trọn 3 điểm",
                          "note": "có thể suy ra từ đội thắng, không nên làm câu kết"})

    # 缺项
    absent = []
    if not final_provided:
        absent.append("tỷ số chung cuộc")
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

    # 标题候选
    title_candidates = []
    if decider:
        if decider.get("own_goal"):
            # 修1:乌龙球决胜 → 标题聚焦受益方,不把乌龙球员当主角
            ben_team = home if decider.get("beneficiary") == "home" else away
            title_candidates.append(f"{ben_team} thắng nhờ phản lưới nhà")
        else:
            title_candidates.append(f"{decider['player']} (bàn quyết định)")
    for pname, cnt in scorer_count.items():
        if cnt >= 2:
            label = "lập cú đúp" if cnt == 2 else "hat-trick"
            title_candidates.append(f"{pname} ({label})")
    if comeback:
        title_candidates.append("(ngược dòng)")
    # 修7:被罚下人数按队合并(两队各算,合并成"thiếu N người")
    sent_off = {}
    for e in events:
        if e.get("type") in ("red", "second_yellow"):
            sent_off[e.get("team")] = sent_off.get(e.get("team"), 0) + 1
    for tm, n in sent_off.items():
        tn = home if tm == "home" else away
        if n >= 2:
            title_candidates.append(f"{tn} chơi thiếu {n} người")
        else:
            title_candidates.append(f"{tn} chơi thiếu người")
    # 修2:点球大战 → 给出点球比分
    if pen_winner and isinstance(pens, (list, tuple)) and len(pens) == 2:
        if pen_winner == "home":
            pen_score = f"{pens[0]}-{pens[1]}"
        else:
            pen_score = f"{pens[1]}-{pens[0]}"
        ptw = home if pen_winner == "home" else away
        title_candidates.append(f"{ptw} thắng {pen_score} trên chấm luân lưu")

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
        "penalties": (list(pens) if isinstance(pens, (list, tuple)) and len(pens) == 2 else None),
        "home_name": home,
        "away_name": away,
        "final_provided": final_provided,
        "order_reliable": order_reliable,
        "missed_penalties": missed_pens,
        "competition_type": comp_type or None,
        "is_knockout": is_knockout,
        "pen_warning": pen_warn,
        "team_errors": sorted(set(team_err)),
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
    """把预处理结果格式化成注入的**纯数据**文本(B1-B4)。

    要求:不含 ** / → / "dùng cho" / "dùng đúng" 等指令性标记;
    进球过程以**球队**作主语;写作提示单独成段并标注不得进入正文。
    """
    hn = result.get("home_name", "đội nhà")
    an = result.get("away_name", "đội khách")

    def _side(s):
        return hn if s == "home" else an

    res = result.get("final", "")
    fh, fa = (res.split("-") if "-" in res else (None, None))
    out = []

    # ---- B1 赛果 ----
    out.append(f"Chủ nhà: {hn} · Khách: {an}")
    if not result.get("final_provided") or fh is None:
        out.append("Kết quả: (chưa có tỷ số chung cuộc)")
    else:
        ih, ia = int(fh), int(fa)
        pw = result.get("penalty_winner")
        pens = result.get("penalties")
        if ih == ia:
            base = "Hai đội hòa " + res
            if pw and pens:
                psc = f"{pens[0]}-{pens[1]}" if pw == "home" else f"{pens[1]}-{pens[0]}"
                base += f" sau 90 phút; {_side(pw)} thắng {psc} trên chấm luân lưu"
            out.append("Kết quả: " + base)
        else:
            wname = hn if ih > ia else an
            # 赢者在前(大比分在前) + 按场地写法(主队在前)
            wbig = f"{max(ih, ia)}-{min(ih, ia)}"
            out.append(f"Kết quả: {wname} thắng {wbig} "
                       f"(viết theo sân: {hn} {ih}-{ia} {an})")

    # ---- B2 进球过程(球队作主语) ----
    reliable = result.get("order_reliable", True)
    header = "Diễn biến:" if reliable else "Sự kiện (không đủ phút để xếp thứ tự):"
    out.append(header)
    timeline = []
    for s in result["score_progression"]:
        timeline.append((parse_minute(s["minute"]), "goal", s))
    for e in result.get("discipline", []):
        timeline.append((parse_minute(e["minute"]), "disc", e))
    timeline.sort(key=lambda x: (x[0] is None, x[0] if x[0] is not None else 0))

    for _, kind, s in timeline:
        mn = f"{s['minute']}'" if s["minute"] is not None else "(?)"
        if kind == "goal":
            team = _side(s.get("team"))
            tail = []
            if s.get("penalty"):
                tail.append("phạt đền")
            if s.get("assist"):
                tail.append(f"kiến tạo: {s['assist']}")
            extra = f" ({'; '.join(tail)})" if tail else ""
            if reliable:
                sh, sa = map(int, s["score"].split("-"))
                tsc = f"{sh}-{sa}" if s.get("team") == "home" else f"{sa}-{sh}"
                if s.get("own_goal"):
                    scorer_side = _side("away" if s.get("team") == "home" else "home")
                    out.append(f"- {mn}: {team} {s['verb']} {tsc} — "
                               f"{s['player']} ({scorer_side}) phản lưới nhà{extra}")
                else:
                    who = f" — {s['player']}" if s.get("player") else ""
                    out.append(f"- {mn}: {team} {s['verb']} {tsc}{who}{extra}")
            else:
                # 缺分钟:只列"球员 + 球队",不写球队作主语的动词短语(B4)
                if s.get("own_goal"):
                    scorer_side = _side("away" if s.get("team") == "home" else "home")
                    out.append(f"- {mn}: {s['player']} ({scorer_side}) phản lưới nhà, "
                               f"có lợi cho {team}{extra}")
                else:
                    out.append(f"- {mn}: {s.get('player','')} ({team}){extra}")
        else:
            team = _side(s.get("team"))
            label = "thẻ vàng thứ hai (bị truất quyền)" if s["kind"] == "second_yellow" else "thẻ đỏ"
            out.append(f"- {mn}: {team} — {s['player']} ({label})")

    if result.get("missed_penalties"):
        out.append("Đá hỏng phạt đền: " + ", ".join(
            f"{m['player']}" + (f" ({m['minute']}')" if m.get("minute") is not None else "")
            for m in result["missed_penalties"]))

    # ---- B3 写作提示(单独成段,标注不得进入正文) ----
    notes = []
    d = result.get("decider")
    if d:
        if d.get("own_goal"):
            notes.append(f"Bàn quyết định: {d['minute']}' — phản lưới nhà của "
                         f"{d['player']} ({_side('away' if d.get('beneficiary') == 'home' else 'home')}), "
                         f"có lợi cho {_side(d.get('beneficiary'))}")
        else:
            mn = f"{d['minute']}'" if d["minute"] is not None else "(không rõ phút)"
            notes.append(f"Bàn quyết định: {mn} {d['player']}")
    if result.get("comeback"):
        notes.append("Tình huống: ngược dòng")
    if any((base_minute(s["minute"]) is not None and 91 <= base_minute(s["minute"]) <= 120)
           for s in result["score_progression"]):
        notes.append(f"Trận có hiệp phụ (ghi kết quả theo 'sau 120 phút': {res})")
    if result.get("pen_warning"):
        notes.append(f"Bỏ qua dữ kiện luân lưu: {result['pen_warning']}")
    if result.get("team_errors"):
        notes.append("Bỏ qua sự kiện có tên đội không khớp: " + ", ".join(result["team_errors"]))
    if not result.get("final_provided"):
        notes.append("Không suy đoán thắng/thua hay bảng xếp hạng (thiếu tỷ số chung cuộc)")
    if result.get("score_mismatch"):
        notes.append(f"Tỷ số công bố ({result.get('final')}) không khớp diễn biến "
                     f"({result.get('events_score')}) — không suy luận thắng/thua")
    if not reliable:
        notes.append("Không suy đoán thứ tự bàn thắng/bàn quyết định (thiếu phút)")
    known = [x for x in ["tỷ số hiệp một"] if any(dd.get("fact") == "tỷ số hiệp một"
                                                 for dd in result.get("derivable", []))]
    if known:
        notes.append("Đã suy ra, không viết thành câu riêng: " + ", ".join(known))
    if not result.get("is_knockout") and result.get("derivable"):
        if any(dd.get("fact") == "giành trọn 3 điểm" for dd in result["derivable"]):
            notes.append("Đã suy ra, không viết thành câu riêng: giành trọn 3 điểm")
    absent = [a for a in result.get("absent", []) if a != "tỷ số chung cuộc"]
    if absent:
        notes.append("Không có dữ kiện (bỏ qua, không nhắc tới): " + ", ".join(absent))
    if result.get("title_candidates"):
        notes.append("Gợi ý tiêu đề: " + " / ".join(result["title_candidates"]))
    if notes:
        out.append("")
        out.append("Ghi chú cho người viết (KHÔNG đưa vào bài):")
        for n in notes:
            out.append("- " + n)

    if warns:
        out.append("")
        out.append("Cảnh báo dữ kiện gốc:")
        for w in warns:
            out.append("- " + w["msg"])

    return "\n".join(out)


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
