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
WATCH = ["quyết định cục diện", "mạch trận", "tâm điểm"]
# 只针对"同一名球员领到第二张黄牌被罚下"这种不规范表述;
# "全队 nhận 2 thẻ vàng" 是正常写法,不该报。
# 用单条正则,避免重叠匹配报两次。
# 只针对"同一名球员领到第二张黄牌被罚下"的不规范表述;
# 全队"nhận 2 thẻ vàng"是正常写法,不该报。
# 判据:用"nhận 2/hai thẻ vàng"表述 且 同句出现需要具体化罚下语境的信号
#       (bị truất quyền/đuổi/loại/thiếu người) → 提示改为"thẻ vàng thứ hai"
DISCIPLINE_BAD = [r"nhận\s+(?:2|hai)\s+thẻ\s+vàng"]
DISCIPLINE_SUGGEST = "nhận thẻ vàng thứ hai"

# 可推导事实(结尾复述用)
RESTATE = ["giành trọn 3 điểm", "ra về với 3 điểm", "giành trọn ba điểm",
           "có được 3 điểm"]
# 事件动词(先预告再展开用)
PREVIEW_VERBS = ["có bàn gỡ", "có bàn thắng", "có bàn rút ngắn", "có bàn nâng tỷ số"]
# 情绪词
GOAL_VERBS = ["mở tỷ số", "gỡ hòa", "san bằng", "vượt lên dẫn", "nâng tỷ số",
              "nhân đôi cách biệt", "rút ngắn cách biệt"]


# 常见缩写(句点不作为句末):TP., HLV., P., T., Q., KS., Th.S, v.v.
_ABBREV = re.compile(r"\b(?:TP|HLV|P|T|Q|KS|Th|GS|TS|NXB|CLB|VĐV|TTXVN)\.$", re.I)


def split_sentences(text):
    """按 .!?… 和换行切句;避开常见缩写(TP./HLV. 等)。返回句子列表(去空)。"""
    raw = re.split(r"(?<=[.!?…])\s+|\n+", text)
    out, buf = [], ""
    for s in raw:
        s = s.strip()
        if not s:
            continue
        buf = (buf + " " + s).strip() if buf else s
        # 若这一段以缩写结尾,则不视为句末,与下一段合并
        if _ABBREV.search(buf):
            continue
        out.append(buf)
        buf = ""
    if buf:
        out.append(buf)
    return out


def _has_minute(s):
    return bool(re.search(r"phút\s+\d+", s, re.I))


def _scores_in(s):
    """返回句中的比分(保持书写顺序的两种解释都给出)。"""
    out = []
    for m in re.finditer(r"(\d)\s*[-–]\s*(\d)", s):
        out.append((int(m.group(1)), int(m.group(2))))
    return out


def normalize_output(text):
    """C1:清理模型输出里的表层 markdown(首行标题的 ** 或 #),不调用模型。

    在 check() 之前、生成之后执行。清理后仍有 markdown 才判 S11。
    """
    lines = text.split("\n")
    # 找到第一个非空行(标题)
    for i, l in enumerate(lines):
        if l.strip():
            s = l.strip()
            # 去掉整体包裹的 **...** 或 # 前缀
            s2 = s
            if s2.startswith("**") and s2.endswith("**") and len(s2) > 4:
                s2 = s2[2:-2].strip()
            if s2.startswith("#"):
                s2 = s2.lstrip("#").strip()
            lines[i] = s2
            break
    return "\n".join(lines).strip()


def check(task_text, facts=None, task=None):
    """返回疑点列表。每条: {rule, snippet, msg}。

    忽略以 # 或 > 开头的元信息行(来自回归样本的注释/引言),避免被当成标题。
    """
    # 先删注释/引言行(回归样本的元信息),再 normalize(避免 # 被 normalize 吃掉后漏删)
    task_text = "\n".join(l for l in task_text.split("\n")
                          if not l.lstrip().startswith(("#", ">")))
    task_text = normalize_output(task_text)
    issues = []
    sents = split_sentences(task_text)
    lines = [l for l in task_text.split("\n") if l.strip()]
    title = lines[0] if lines else ""

    # ---- S1 比分动词矛盾(需 facts) ----
    if facts:
        try:
            from prepare_facts import compute
            result = compute(facts)
            # C2:顺序不可靠时,只核对单独一条带分钟的进球;
            #    且期望动词不含 '?'(缺分钟时不推断动词)
            _reliable = result.get("order_reliable", True)
            _skip_s1 = False
            if not _reliable:
                # 顺序不可靠:correct_map 只放**有分钟且动词非 ?** 的进球
                _with_min = [s for s in result["score_progression"]
                             if s["minute"] is not None and not str(s["verb"]).startswith("?")]
                if len(_with_min) != 1:
                    _skip_s1 = True
            # 凡动词以 ? 开头(含 '? (phản lưới nhà)')一律排除
            correct_map = ({} if _skip_s1 else
                           {s["score"]: s["verb"]
                            for s in result["score_progression"]
                            if s["minute"] is not None and not str(s["verb"]).startswith("?")})
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
                        alt_txt = f" (hoặc cách viết thay thế được chấp nhận: {', '.join(alts)})" if alts else ""
                        issues.append({"rule": "S1", "snippet": f"{used[0]} ... {key}",
                                       "msg": f"Tỷ số {key} phải dùng '{correct}'{alt_txt}, "
                                       f"nhưng bài dùng '{used[0]}'"})
        except Exception as e:
            issues.append({"rule": "S1", "snippet": "-", "msg": f"Lỗi xử lý facts: {e}"})

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
            issues.append({"rule": "S2", "snippet": cur[:50], "hint_only": True,
                           "msg": f"Tỷ số {key} đã xuất hiện ở câu trước, câu này nhắc lại (trùng lặp)"})

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
        # 前句若已含比分(说明它本身在陈述结果,不是纯预告) → 跳过
        if _scores_in(cur):
            continue
        # 后句含分钟且是事件句
        if _has_minute(nxt) and any(w in nxt.lower() for w in EVENT_WORDS):
            issues.append({"rule": "S3", "snippet": cur[:50], "hint_only": True,
                           "msg": "Báo trước rồi kể lại cùng một sự kiện (câu trước không có phút, câu sau mới kể chi tiết)"})

    # ---- S4 结尾复述 ----
    if sents:
        last = sents[-1]
        # 末段只含复述,无新实体/数字
        has_restate = any(r in last.lower() for r in RESTATE)
        # 简单判断"无新信息":长度短且含比分或复述词
        # 规则卡要求结尾写"积分榜后果",这类句不算复述
        standings = bool(re.search(r"(lên thứ|xếp thứ|vươn lên|bảng xếp hạng|"
                                   r"thứ \d|giữ ngôi|đội đầu|top \d)", last, re.I))
        if not standings and (has_restate or
                              (len(last) < 80 and _scores_in(last) and _has_minute(last) is False)):
            # 排除末句是新事实(含新球员名/新事件)
            fresh = bool(re.search(r"(thay|vào sân|chấn thương|tuyên bố|phát biểu)", last, re.I))
            if not fresh:
                issues.append({"rule": "S4", "snippet": last[:60], "hint_only": True,
                               "msg": "Kết bài nhắc lại kết quả/điểm số, không có thông tin mới (nên bỏ hoặc thay bằng hệ quả bảng xếp hạng)"})

    # ---- S5 内部/模糊描述 ----
    for v in VAGUE:
        if v in task_text.lower():
            issues.append({"rule": "S5", "snippet": v,
                           "msg": f"Cụm mô tả nội bộ/mơ hồ '{v}', nên bỏ hoặc thay bằng thông tin cụ thể"})

    # ---- S6 纪律术语 ----
    # 判据(优先用 facts):句中出现 facts 的 second_yellow 球员名 + "nhận 2/hai thẻ vàng"
    #   → 提示改为 "thẻ vàng thứ hai"。全队两张黄牌的写法不报。
    # 无 facts 时退回语境判据(同句含 罚下/少一人 等信号)。
    second_yellow_players = []
    if facts:
        try:
            for e in facts.get("events", []):
                if e.get("type") in ("second_yellow", "red") and e.get("player"):
                    second_yellow_players.append(e["player"])
        except Exception:
            pass
    DISCIPLINE_CTX = re.compile(r"(truất quyền|bị đuổi|bị loại|thiếu người|thẻ đỏ|"
                                r"thẻ vàng thứ hai|hai lần nhận thẻ)", re.I)
    for pat in DISCIPLINE_BAD:
        for m in re.finditer(pat, task_text, re.I):
            # 取同句上下文
            s0 = task_text.rfind(".", 0, m.start()) + 1
            s1 = task_text.find(".", m.end())
            sent = task_text[s0:(s1 if s1 != -1 else len(task_text))]
            # facts 判据:句中含被罚下球员名(全名或后缀,越南媒体常只写后两音节)
            def _name_hit(sentence, full):
                if not full:
                    return False
                if full in sentence:
                    return True
                toks = str(full).split()
                # 依次尝试后缀 2/1 个音节(如 "Nguyễn Quốc Dân" → "Quốc Dân" / "Dân")
                for k in (2, 1):
                    if len(toks) > k:
                        tail = " ".join(toks[-k:])
                        if len(tail) >= 3 and tail in sentence:
                            return True
                return False
            by_player = any(_name_hit(sent, pl) for pl in second_yellow_players)
            # 语境判据:同句有罚下/少一人信号
            by_ctx = bool(DISCIPLINE_CTX.search(sent))
            if by_player or by_ctx:
                issues.append({"rule": "S6", "snippet": m.group(0), "hint_only": True,
                               "msg": "Cách viết 'nhận 2 thẻ vàng' là chấp nhận được; "
                                      "biên tập có thể cân nhắc 'nhận thẻ vàng thứ hai' / "
                                      "'bị truất quyền thi đấu' nếu muốn trang trọng hơn"})

    # ---- S7 情绪词密度 ----
    n = len(task_text)
    hit = [w for w in EMOTION if w in task_text.lower()]
    if n > 0:
        per_k = len(hit) / (n / 1000.0)
        if per_k > 3:      # 每千字超 3 个情绪词
            issues.append({"rule": "S7", "snippet": ", ".join(hit[:5]), "hint_only": True,
                           "msg": f"Mật độ từ cảm xúc cao ({len(hit)} từ / {n} ký tự), tin tức nên trung tính"})

    # ---- S8 待审搭配(去重:同一片段只报一次) ----
    seen_watch = set()
    for w in WATCH:
        if w in seen_watch:
            continue
        seen_watch.add(w)
        if w in task_text.lower():
            issues.append({"rule": "S8", "snippet": w, "hint_only": True,
                           "msg": f"Cụm từ cần biên tập xác nhận '{w}'"})

    # ---- S9 标题决胜事件(需 facts) ----
    if facts:
        try:
            from prepare_facts import compute
            result = compute(facts)
            d = result.get("decider")
            if d and title:
                # 乌龙球决胜:标题不该把乌龙球员当主角(应聚焦受益方)
                if d.get("own_goal"):
                    og_parts = [x for x in (d["player"] or "").split() if len(x) >= 1]
                    if og_parts and any(x in title for x in og_parts):
                        ben = d.get("beneficiary")
                        ben_name = facts.get("home" if ben == "home" else "away", "")
                        issues.append({
                            "rule": "S9", "snippet": title[:50],
                            "msg": f"Tiêu đề lấy cầu thủ đá phản lưới nhà '{d['player']}' "
                                   f"làm nhân vật chính; nên tập trung vào đội hưởng lợi "
                                   f"'{ben_name}'"})
                # 标题应含决胜球员名(乌龙球时跳过——主角是受益方,不是乌龙球员)
                pl = "" if d.get("own_goal") else (d["player"] or "")
                STOP2 = {"quốc", "gia", "cúp", "đội", "trận", "bàn", "phút"}
                parts = [x for x in pl.split() if len(x) > 2 and x.lower() not in STOP2]
                if parts and not any(x in title for x in parts):
                    issues.append({"rule": "S9", "snippet": title[:50],
                                   "msg": f"Tiêu đề không có cầu thủ ghi bàn quyết định '{pl}'"})
                # 反向:标题把"非决胜的进球者"也列为主角(与决胜球员并列)
                dec_parts = set(parts)
                for s in result["score_progression"]:
                    if s["player"] == pl:
                        continue        # 跳过决胜球员本身
                    # 过滤:短于 4 字符的 token(如 "Quốc")易与"Cúp Quốc gia"等词撞车
                    STOP = {"quốc", "gia", "cúp", "đội", "trận", "bàn", "phút"}
                    s_parts = [x for x in s["player"].split()
                               if len(x) > 3 and x.lower() not in STOP]
                    if not s_parts:
                        continue
                    if any(x in title for x in s_parts) and (not parts or
                            any(x in title for x in parts)):
                        # 标题同时含非决胜球员和决胜球员 → 并列嫌疑
                        if any(x in title for x in parts):
                            issues.append({
                                "rule": "S9", "snippet": title[:50],
                                "msg": f"Tiêu đề đặt cầu thủ không quyết định '{s['player']}' ngang hàng với cầu thủ quyết định, nên chỉ nêu cầu thủ quyết định"})
                            break
        except Exception:
            pass

    # ---- S10 汉字混入(直接阻断级) ----
    han = re.findall(r"[\u4e00-\u9fff]+", task_text)
    if han:
        issues.append({"rule": "S10", "snippet": ", ".join(han[:5]), "blocking": True,
                       "msg": f"Bài viết lẫn chữ Hán: {', '.join(han[:5])} — phải sửa"})

    # ---- S11 markdown 残留(事实块的 ** 等被抄进正文) ----
    md = []
    if "**" in task_text:
        md.append("**")
    for pat, label in ((r"^\s*[-•]\s+\S", "gạch đầu dòng"),
                       (r"^\s*#{1,6}\s", "tiêu đề markdown"),
                       (r"`[^`]+`", "code")):
        if re.search(pat, task_text, re.M):
            md.append(label)
    if md:
        issues.append({"rule": "S11", "snippet": ", ".join(md), "blocking": True,
                       "msg": f"Bài viết còn dấu vết markdown/định dạng nội bộ: {', '.join(md)}"})

    # ---- S12 时间词与分钟矛盾(按句判断,C4) ----
    TIME_WORDS = {
        "phút cuối": (85, 90), "cuối trận": (80, 90), "những phút cuối": (80, 90),
        "giai đoạn cuối trận": (80, 90), "thời khắc cuối trận": (80, 90),
        "phút cuối chung cuộc": (85, 90),
        "hiệp một": (1, 45), "hiệp 1": (1, 45), "đầu trận": (1, 15),
        "khung giờ thứ hai": (46, 90), "hiệp hai": (46, 90), "hiệp 2": (46, 90),
    }
    # 先按句切分;同一句里同时有时间词与分钟,且所有分钟都不在范围内 → 报
    for sent in split_sentences(task_text):
        low = sent.lower()
        # 时间范围说法("từ … cho đến (trước) phút X")不算时间词矛盾
        if re.search(r"từ\s+.{0,30}(cho đến|đến|tới)\s+(trước\s+)?phút", low):
            continue
        mins = []
        for m in re.finditer(r"phút\s+(\d{1,3})(?:\s*\+\s*(\d+))?", low):
            mins.append(int(m.group(1)))
        if not mins:
            continue
        for w, (lo, hi) in TIME_WORDS.items():
            if w in low:
                if not any(lo <= x <= hi for x in mins):
                    issues.append({"rule": "S12", "hint_only": True,
                                   "snippet": f"phút {mins[0]} ... {w}",
                                   "msg": f"Các phút {mins} trong câu không khớp với "
                                          f"cụm thời gian '{w}' (khoảng {lo}-{hi})"})
                break

    # ---- S13 主客场方向(需 facts) ----
    if facts:
        try:
            hn = facts.get("home")
            an = facts.get("away")
            fin = facts.get("final")
            if hn and an and fin:
                fh, fa = int(fin[0]), int(fin[1])
                home_won = fh > fa
                away_won = fa > fh
                wname = hn if home_won else (an if away_won else None)
                lname = an if home_won else (hn if away_won else None)
                # "X đón tiếp Y" / "tại nhà" 结构里,接待方应是主队
                for m in re.finditer(r"([A-ZĐ][\w\sÀ-ỹ]{1,25}?)\s+đón tiếp\s+([A-ZĐ][\w\sÀ-ỹ]{1,25}?)[\s.,]", task_text):
                    a, b = m.group(1).strip(), m.group(2).strip()
                    if hn.lower() in b.lower() and an.lower() in a.lower():
                        issues.append({"rule": "S13", "hint_only": True,
                                       "snippet": m.group(0)[:60],
                                       "msg": f"'{a} đón tiếp {b}' nhưng chủ nhà là {hn}"})
                # lname thắng/nghiêng về chủ nhà 类错误
                if lname and re.search(re.escape(lname) + r"[^.]{0,25}(thắng|nghiêng về)", task_text, re.I):
                    if re.search(r"chủ nhà", task_text, re.I):
                        issues.append({"rule": "S13", "hint_only": True, "snippet": lname,
                                       "msg": f"Kiểm tra hướng kết quả: {lname} là đội thua"})
                # "đội chủ nhà chơi thiếu người" 但红牌是客队
                reds = [e for e in facts.get("events", []) if e.get("type") in ("red", "second_yellow")]
                if reds and re.search(r"đội chủ nhà[^.]{0,20}thiếu người", task_text, re.I):
                    red_side = reds[0].get("team")
                    if red_side == "away":
                        issues.append({"rule": "S13", "hint_only": True,
                                       "snippet": "đội chủ nhà ... thiếu người",
                                       "msg": f"Thẻ phạt thuộc đội khách ({an}), không phải chủ nhà"})
        except Exception:
            pass

    # ---- S14 专有名词核对(正文与 facts/任务描述比对) ----
    if facts or task:
        try:
            import unicodedata as _ud
            def _bucket(x):
                return _ud.normalize("NFC", str(x)).casefold()
            # 允许的专有名词集合:facts 名字 + facts["context"] + 任务文本大写词串(C3)
            allowed = set()
            facts = facts or {}
            if task:
                for m in re.finditer(r"\b[A-ZĐ][\wÀ-ỹ]+(?:\s+[A-ZĐ][\wÀ-ỹ]+)*", task):
                    for tok in m.group(0).split():
                        allowed.add(_bucket(tok))
            for v in (facts.get("home"), facts.get("away")):
                if v:
                    for tok in str(v).split():
                        allowed.add(_bucket(tok))
            for e in facts.get("events", []):
                for k in ("player", "assist"):
                    if e.get(k):
                        for tok in str(e[k]).split():
                            allowed.add(_bucket(tok))
            ctx = facts.get("context")
            if ctx:
                for tok in str(ctx).split():
                    allowed.add(_bucket(tok))
            # 正文里的"看起来像教练/官员"的专有名词
            # 允许集合里存的是"整名"(去变音小写),按整名或≥2 token 匹配
            full_names = set()
            for v in (facts.get("home"), facts.get("away")):
                if v:
                    full_names.add(_bucket(v))
            for e in facts.get("events", []):
                for k in ("player", "assist"):
                    if e.get(k):
                        full_names.add(_bucket(e[k]))
            if task:
                # 从 task 里提取"HLV/Huấn luyện viên + 名字"以及连续大写词串
                for m in re.finditer(r"\b(?:HLV|huấn luyện viên)\s+([A-ZĐ][\wÀ-ỹ]*(?:\s+[A-ZĐ][\wÀ-ỹ]*){1,3})", task):
                    full_names.add(_bucket(m.group(1)))
                for m in re.finditer(r"\b[A-ZĐ][\wÀ-ỹ]+(?:\s+[A-ZĐ][\wÀ-ỹ]+)+", task):
                    full_names.add(_bucket(m.group(0)))
            for m in re.finditer(r"\b(HLV|huấn luyện viên)\s+([A-ZĐ][\wÀ-ỹ]*(?:\s+[A-ZĐ][\wÀ-ỹ]*){1,3})", task_text):
                name = m.group(2).strip()
                nb = _bucket(name)
                matched = nb in full_names or any(
                    fn.startswith(nb) or nb.startswith(fn) for fn in full_names if len(fn) >= 5)
                if not matched:
                    issues.append({"rule": "S14", "hint_only": True,
                                   "snippet": name[:50],
                                   "msg": f"Tên riêng '{name}' không có trong dữ kiện → kiểm tra bịa đặt"})
            # 扩展: "sân + 专名"、"người + 国籍"、"bảng + 字母"
            for m in re.finditer(r"\bsân\s+([A-ZĐ][\wÀ-ỹ]+(?:[ \t]+[A-ZĐ][\wÀ-ỹ]+)*)", task_text):
                nm = m.group(1).strip()
                # 队名可作球场名("sân Thể Công"); 只要 token 命中允许集合就不报
                ntoks = [_bucket(x) for x in nm.split()]
                if not any(tk in " ".join(full_names) for tk in ntoks) and _bucket(nm) not in full_names:
                    issues.append({"rule": "S14", "hint_only": True, "snippet": m.group(0)[:40],
                                   "msg": f"Tên sân '{nm}' không có trong dữ kiện → kiểm tra bịa đặt"})
            for m in re.finditer(r"người\s+(Uruguay|Brazil|Argentina|Hàn Quốc|Nhật Bản|"
                                 r"Thái Lan|Trung Quốc|Pháp|Đức|Ý|Tây Ban Nha|Anh|Bồ Đào Nha)",
                                 task_text, re.I):
                issues.append({"rule": "S14", "hint_only": True, "snippet": m.group(0),
                               "msg": f"Thông tin quốc tịch '{m.group(0)}' — kiểm tra có trong dữ kiện không"})
            for m in re.finditer(r"\bbảng\s+([A-D])\b", task_text):
                issues.append({"rule": "S14", "hint_only": True, "snippet": m.group(0),
                               "msg": f"'{m.group(0)}' (chia bảng) — kiểm tra giải có chia bảng không"})
        except Exception:
            pass

    import unicodedata as _ud2
    def _strip(x):
        return "".join(c for c in _ud2.normalize("NFD", str(x))
                       if _ud2.category(c) != "Mn").lower()

    # ---- S21 数据行泄漏(阻断) ----
    # 按句判断(段中夹的比分行也要拦);只用 facts 的两个队名做精确匹配
    hn21 = (facts or {}).get("home") if facts else None
    an21 = (facts or {}).get("away") if facts else None
    for sent in split_sentences(task_text):
        s = sent.strip()
        if not s:
            continue
        # ① 'Kết quả:' 开头,不论位置
        if re.match(r"^Kết quả\s*:", s, re.I):
            issues.append({"rule": "S21", "blocking": True, "snippet": s[:50],
                           "msg": "Dòng dữ liệu lọt vào bài ('Kết quả: …')"})
            continue
        # ② 整句只有 '队A 比分 队B'(队名取自 facts,精确)
        if hn21 and an21:
            pat = (r"^(?:" + re.escape(hn21) + r"|" + re.escape(an21) + r")\s+"
                   r"\d+\s*-\s*\d+\s+"
                   r"(?:" + re.escape(hn21) + r"|" + re.escape(an21) + r")\.?$")
            if re.match(pat, s):
                issues.append({"rule": "S21", "blocking": True, "snippet": s[:50],
                               "msg": "Câu chỉ có 'đội - tỷ số - đội' (lọt từ dữ liệu)"})

    # ---- S15 赛果方向(需 facts) ----
    if facts:
        try:
            fin = facts.get("final")
            hn2, an2 = facts.get("home"), facts.get("away")
            if fin and hn2 and an2:
                fh2, fa2 = int(fin[0]), int(fin[1])
                is_draw = (fh2 == fa2)
                # ① 非平局却写"trận hòa / hòa nhau"
                if not is_draw and re.search(r"trận hòa|hòa nhau|chia điểm", task_text, re.I):
                    issues.append({"rule": "S15", "blocking": True,
                                   "snippet": "trận hòa", "msg": "Trận đấu không hòa — không viết 'trận hòa'"})
                # ② nghiêng về chủ nhà/đội khách 与赛果矛盾
                if not is_draw:
                    if fh2 < fa2 and re.search(r"nghiêng về\s+(phía\s+)?chủ nhà", task_text, re.I):
                        issues.append({"rule": "S15", "blocking": True,
                                       "snippet": "nghiêng về chủ nhà",
                                       "msg": f"Đội khách ({an2}) thắng, không phải chủ nhà"})
                    if fh2 > fa2 and re.search(r"nghiêng về\s+(phía\s+)?đội khách", task_text, re.I):
                        issues.append({"rule": "S15", "blocking": True,
                                       "snippet": "nghiêng về đội khách",
                                       "msg": f"Đội chủ nhà ({hn2}) thắng, không phải đội khách"})
                # ③ 胜者作主语后 30 字符内出现小比分在前的比分
                for m in re.finditer(r"(thắng|đánh bại|hạ)\s+[^.]{0,30}?\b(\d)-(\d)\b", task_text, re.I):
                    a2, b2 = int(m.group(2)), int(m.group(3))
                    if a2 < b2:
                        issues.append({"rule": "S15", "blocking": True,
                                       "snippet": m.group(0)[:50],
                                       "msg": "Đội thắng làm chủ ngữ phải ghi tỷ số lớn trước"})
        except Exception:
            pass

    # ---- S16 进球数(需 facts) ----
    if facts:
        try:
            cnt = {}
            for e in facts.get("events", []):
                if e.get("type") in ("goal", "penalty") and e.get("player"):
                    cnt[e["player"]] = cnt.get(e["player"], 0) + 1
            import unicodedata as _ud2
            def _strip(x):
                return "".join(c for c in _ud2.normalize("NFD", str(x))
                               if _ud2.category(c) != "Mn").lower()
            for pl, c in cnt.items():
                if c == 1:
                    # 只针对"单人"梅开二度措辞;'hai bàn thắng của A và B' 是两人各一球,不算
                    for m in re.finditer(r"cú đúp|hat-?trick|lập công hai lần", task_text, re.I):
                        raw = task_text[max(0, m.start() - 40):m.end() + 40]
                        seg = _strip(raw)
                        toks = [_strip(x) for x in pl.split() if len(_strip(x)) > 2]
                        # 若窗口里出现"và"(两人并列)则跳过
                        if " và " in raw.lower():
                            continue
                        if any(x in seg for x in toks):
                            issues.append({"rule": "S16", "blocking": True,
                                           "snippet": raw[:50],
                                           "msg": f"{pl} chỉ ghi 1 bàn — không dùng 'cú đúp/hat-trick'"})
        except Exception:
            pass

    # ---- S17 决胜球归属(需 facts) ----
    if facts:
        try:
            from prepare_facts import compute as _compute
            r17 = _compute(facts)
            d17 = r17.get("decider")
            for m in re.finditer(r"bàn\s+(thắng\s+)?quyết định", task_text, re.I):
                if not r17.get("order_reliable"):
                    issues.append({"rule": "S17", "hint_only": True, "snippet": m.group(0),
                                   "msg": "Thiếu phút để xác định bàn quyết định — kiểm tra lại"})
                    continue
                if d17 and d17.get("player"):
                    seg = _strip(task_text[max(0, m.start() - 60):m.end() + 60])
                    toks = [_strip(x) for x in d17["player"].split() if len(_strip(x)) > 2]
                    if toks and not any(x in seg for x in toks):
                        issues.append({"rule": "S17", "blocking": True,
                                       "snippet": seg[:50],
                                       "msg": f"Bàn quyết định thuộc {d17['player']}, không phải nhân vật trong câu"})
        except Exception:
            pass

    # ---- S18 元说明(向读者解释规则/数据) ----
    META_PATTERNS = [
        r"không phải tỷ số", r"là kết quả (của )?loạt luân lưu", r"trước loạt luân lưu",
        r"cũng là bàn quyết định", r"theo dữ kiện", r"dữ liệu được cung cấp",
    ]
    for pat in META_PATTERNS:
        for m in re.finditer(pat, task_text, re.I):
            issues.append({"rule": "S18", "blocking": True, "snippet": m.group(0),
                           "msg": f"Không giải thích quy tắc/dữ liệu cho người đọc ('{m.group(0)}')"})

    # ---- S22 因果补写(提示;复用 check_fabrication 的因果检测) ----
    if facts or task:
        try:
            import importlib.util as _ilu, pathlib as _pl2
            _fp = _pl2.Path(__file__).resolve().parent / "check_fabrication.py"
            _spec = _ilu.spec_from_file_location("_cf", _fp)
            _cf = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_cf)
            # 参照 = 任务描述 + facts 全部文本(含 context/事件细节),避免把有依据的因果误判
            src_parts = [task or ""]
            if facts:
                src_parts.append(json.dumps(facts, ensure_ascii=False))
                if facts.get("context"):
                    src_parts.append(str(facts["context"]))
            src = "\n".join(src_parts)
            # 在参照里出现过的因果连接短语视为有依据
            CUE = ["thẻ vàng", "thẻ đỏ", "truất quyền", "VAR", "kiểm tra", "chấn thương",
                   "vắng mặt", "phản lưới", "sút xa", "kiến tạo", "chuyền"]
            found = _cf.find_fabrications(src, task_text)
            for f in found:
                nhom = str(f.get("nhóm", ""))
                if "nhân quả" not in nhom and "causal" not in nhom.lower():
                    continue
                frag = str(f.get("khớp", ""))
                # 若该因果片段附近的线索词在参照里有据 → 跳过
                if any(c.lower() in src.lower() for c in CUE):
                    # 进一步:该片段的前后上下文是否含线索词
                    idx = task_text.find(frag)
                    ctx = task_text[max(0, idx - 60):idx + 60] if idx >= 0 else ""
                    if any(c.lower() in ctx.lower() for c in CUE):
                        continue
                issues.append({"rule": "S22", "hint_only": True,
                               "snippet": frag[:50],
                               "msg": "Nghi bổ sung quan hệ nhân quả không có trong dữ kiện"})
        except Exception:
            pass

    # ---- S19 重复(提示) ----
    ev_seen = {}
    for m in re.finditer(r"(\d{1,3})'", task_text):
        mn = m.group(1)
        seg = task_text[m.start():m.start() + 60]
        key = (mn, seg[:30].strip())
        ev_seen[key] = ev_seen.get(key, 0) + 1
    for (mn, _), n in ev_seen.items():
        if n >= 3:
            issues.append({"rule": "S19", "hint_only": True, "snippet": f"{mn}'",
                           "msg": f"Sự kiện phút {mn}' được nhắc {n} lần — kiểm tra trùng lặp"})

    # ---- S20 动词主语(提示) ----
    team_names = set()
    if facts:
        for v in (facts.get("home"), facts.get("away")):
            if v:
                team_names.add(_strip(v))
    for m in re.finditer(r"([A-ZĐ][\wÀ-ỹ]+(?:\s+[A-ZĐ][\wÀ-ỹ]+)*)\s+"
                         r"(vượt lên dẫn|gỡ hòa|nâng tỷ số|rút ngắn cách biệt)", task_text):
        subj = m.group(1).strip()
        # 队名作主语是正确的 → 排除
        if any(_strip(subj) == tn or _strip(subj) in tn or tn in _strip(subj) for tn in team_names):
            continue
        ctx = task_text[max(0, m.start() - 30):m.start()]
        if not re.search(r"đưa|giúp|mang về|ghi bàn", ctx, re.I):
            issues.append({"rule": "S20", "hint_only": True, "snippet": m.group(0)[:50],
                           "msg": f"'{subj}' không nên làm chủ ngữ trực tiếp — "
                                  f"nên viết 'đưa/giúp {subj} …'"})

    # 去重
    seen_i, uniq_i = set(), []
    for i in issues:
        k = (i["rule"], i["snippet"])
        if k not in seen_i:
            seen_i.add(k)
            uniq_i.append(i)
    return uniq_i


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
