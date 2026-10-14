#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""extract_football.py — 第三阶段:足球素材全量抽取(全文版,支持断点续跑)。

v2 修正(按复审意见):
  问题一 正文只存 300 字符 → 改为**保存全文**到 distill_work/football_full/
         (不进仓库),确认表仍只展示前 300 字符。
  问题二 赛果规则过宽 → 语境词表去掉普通词(giải/đội/hiệp),
         要求命中 ≥2 个**比赛专属**词;并加排除词(排球/篮球/网球/羽毛球/
         五人制/pencak/拳击/乒乓球)。
  问题三 LSH 分桶太粗 → 改为标准分段 LSH(128 哈希 / 32 段 × 4 行),
         任一段相同即进入同一比较桶。

用法:
    python bin/extract_football.py --out distill_football --workers 8
    python bin/extract_football.py --out distill_football --status
    python bin/extract_football.py --out distill_football --merge
"""
import argparse
import hashlib
import json
import re
import sys
import unicodedata
from collections import Counter
from multiprocessing import Pool
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = Path("/lzcapp/document/Knowledge-vietnem/OpenDataLab___WanJuan-Vietnamese/raw")
FULLDIR = ROOT / "distill_work" / "football_full"   # 全文(不进仓库)
CATS = ["ket_qua", "truoc_tran", "chuyen_nhuong", "nhan_vat", "social", "betting"]

# ---- 足球识别 ----
FOOTBALL_KW = re.compile(
    r"bóng đá|tỷ số|ghi bàn|thủ môn|HLV|V\.?League|Ngoại hạng Anh|"
    r"Champions League|đội tuyển|vòng \d+|phút \d+", re.I)

# ---- 比分(严格) ----
# 比分:数字-数字;排除日期(前后紧邻 / 或 . 或 数字)与量词
# 比分判定(不用单一正则,避免误伤"thắng 3-1."这类句末比分)
#   - DATE_RE: 日期模式(05-19 / 12/07/2025 / ngày 7-25) → 先挖掉
#   - UNIT_RE: 量词(1-2 thìa / 5-10 kg) → 先挖掉
#   然后剩下的 \d{1,2}-\d{1,2} 才算比分
DATE_RE = re.compile(
    r"\bngày\s+\d{1,2}[/.-]\d{1,2}(?:[/.-]\d{2,4})?"
    r"|\b\d{2}[/.-]\d{2}[/.-]\d{2,4}\b"
    r"|\b\d{2}[/.-]\d{2}\b(?![\s]*[-–]\s*\d)")   # 独立的 07-25
# 量词：先挖掉"1-2 thìa / 5-10 kg"这类，避免当成比分
# 要点：① 每个单位都要有词边界（否则 tr 会吃掉 trước/trên/trong）
#       ② 不列 phút/giờ —— 足球报道里 "1-0 phút 90"、"1-0 giờ nghỉ" 是比分写法
#       ③ tỷ 用 (?!\s*số) 避免吃掉 "tỷ số"（比分本身）
UNIT_RE = re.compile(
    r"\b\d{1,2}\s*-\s*\d{1,2}\s*(?:"
    r"thìa|kg|g\b|cm|mm|m\b|tuần|ngày|tháng|triệu|nghìn|"
    r"tỷ\b(?!\s*số)|tr\b|tấn|gam|ml|l\b|km|inch|foot|feet"
    r")(?![\wÀ-ỹ])", re.I)
SCORE_RE = re.compile(r"(?<![\d/.])(\d{1,2})\s*-\s*(\d{1,2})(?![\d/])")


def find_scores(text):
    """返回文本里真正的比分(已剔除日期/量词)。"""
    t = DATE_RE.sub(" ", text)
    t = UNIT_RE.sub(" ", t)
    return SCORE_RE.findall(t)

MIN_RE = re.compile(r"(phút\s*\d+|\b\d{1,3}')", re.I)
GOAL_VERB = re.compile(
    r"mở tỷ số|gỡ hòa|nâng tỷ số|rút ngắn cách biệt|vượt lên dẫn|ấn định", re.I)

# ---- 赛果语境:必须是**比赛专属**词(去掉 giải/đội/hiệp 等普通词) ----
MATCH_CTX_TERMS = [
    r"trận đấu", r"ghi bàn", r"bàn thắng", r"thủ môn", r"trọng tài",
    r"thẻ vàng", r"thẻ đỏ", r"HLV", r"huấn luyện viên", r"vòng \d+",
    r"vòng loại", r"V\.?League", r"Cúp", r"chung kết", r"bán kết",
    r"tứ kết", r"sân vận động", r"luân lưu", r"phạt đền", r"penalty",
    r"cầu thủ", r"đội hình", r"hiệp 1", r"hiệp 2", r"hiệp phụ",
    r"bóng đá", r"champions league", r"ngoại hạng anh", r"world cup",
    r"kết thúc với tỷ số", r"tỷ số \d",
]
MATCH_CTX_RES = [re.compile(p, re.I) for p in MATCH_CTX_TERMS]

# ---- 其他球类/项目:出现则不判赛果 ----
# 其他运动项目的球队名(评审建议:NBA/NFL 等)
OTHER_SPORT_TEAMS = re.compile(
    r"\b(?:NBA|NFL|MLB|NHL|76ers|Lakers|Celtics|Warriors|Bucks|Nets|Heat|"
    r"Rockets|Mavericks|Clippers|Nuggets|Suns|Knicks|Bulls|Spurs|Kings|"
    r"Wizards|Hornets|Pistons|Pacers|Cavaliers|Raptors|Grizzlies|Pelicans|"
    r"Thunder|Timberwolves|Blazers|Jazz|Magic|Hawks)\b", re.I)
# 标签聚合页特征(评审建议剔除)
AGGREGATOR_RE = re.compile(
    r"^\s*Tags?\s*[-|]|\|\s*Tags\s*\||^\s*[a-z\s]{3,25}\s*\|\s*Tags\s*\|", re.I)


def is_aggregator(t):
    """标签聚合页/多摘要混杂页(评审要求剔除,不进词组表)。"""
    head = t[:200]
    if AGGREGATOR_RE.search(head):
        return True
    # 大量"X ngày trước"/"X giờ trước"的相对时间 → 聚合页
    return len(re.findall(r"\d+\s*(?:giờ|ngày|phút)\s*trước", head)) >= 2


EXCLUDE_SPORT_RE = re.compile(
    r"bóng chuyền|bóng rổ|quần vợt|cầu lông|bóng bàn|pencak|quyền anh|futsal|"
    r"võ thuật|karate|taekwondo|judo|bơi lội|điền kinh|golf|đua xe|"
    r"cờ vua|billiards|snooker|esport|thể hình|cử tạ", re.I)
FU_COUNT = 0  # futsal 由用户单独决定:暂按"不收录"

# ---- 其他类别 ----
PRE_RE = re.compile(r"nhận định|trước trận|đội hình dự kiến|lực lượng|đối đầu", re.I)
TRANSFER_RE = re.compile(r"chuyển nhượng|chiêu mộ|ký hợp đồng|gia nhập", re.I)
PROFILE_RE = re.compile(r"chân dung|sự nghiệp|tiểu sử", re.I)
BET_RE = re.compile(r"soi kèo|tỷ lệ kèo|tài xỉu|kèo châu Á|nhà cái", re.I)
# 博彩扩充词表（复审要求）
BET_RE2 = re.compile(
    r"cá cược|đặt cược|kèo nhà cái|link vào|W88|Fun88|188bet|nhacai|"
    r"soi kèo|tỷ lệ kèo|tài xỉu|kèo châu Á|nhà cái|kèo cược|bắt kèo|"
    r"dự đoán tỷ số|keonhacai|m88|12bet|bk8|sbobet", re.I)


def is_betting(t):
    return bool(BET_RE2.search(t))


def ket_qua_score(t):
    """赛果稿的排序分（不做硬过滤，改排序）。
    各加分项：首段/标题出现比分；首段出现结果动词；全文 ≥2 个进球分钟。"""
    head = t[:400]          # 首段近似
    score = 0
    # 首段或标题里有比分
    if find_scores(head):
        score += 3
    # 首段出现结果动词
    if GOAL_VERB.search(head) or re.search(
            r"\b(thắng|đánh bại|hạ|hòa|thua|kết thúc)\b", head, re.I):
        score += 2
    # 全文 ≥2 个进球分钟
    mins = MIN_RE.findall(t)
    if len(mins) >= 2:
        score += 2
    elif len(mins) == 1:
        score += 1
    return score


def classify(t):
    # 博彩稿：只打 betting，不进入任何其他类别（也不参与 ngram/名称表统计）
    if is_betting(t):
        return ["betting"]
    # 标签聚合页：剔除,不进任何类别
    if is_aggregator(t):
        return []
    tags = []
    if is_ket_qua(t):
        tags.append("ket_qua")
    if PRE_RE.search(t):
        tags.append("truoc_tran")
    if TRANSFER_RE.search(t):
        tags.append("chuyen_nhuong")
    if PROFILE_RE.search(t):
        tags.append("nhan_vat")
    if len(t) < 600 and re.search(r"[!?]", t):
        tags.append("social")
    return tags

# ---- 年份 ----
TOURNAMENT_RE = re.compile(
    r"\b(?:World Cup|Euro|Asian Cup|AFF Cup|AFF Suzuki Cup|SEA Games|Olympic|"
    r"U-?\d{2}|Copa America|Confederation|Nations League|Vòng loại)"
    r"[\s\w]*?(19[89]\d|20[0-2]\d)\b", re.I)
FULL_DATE_RE = re.compile(r"\bngày\s+\d{1,2}[/.-]\d{1,2}[/.-](19[89]\d|20[0-2]\d)\b", re.I)
# 发布时间格式(优先): "dd/mm/yyyy hh:mm" 或 "dd/mm/yyyy hh:mm GMT+7"
PUBDATE_RE = re.compile(
    r"\b(\d{1,2})[/.-](\d{1,2})[/.-](20[0-2]\d|19[89]\d)"
    r"(?:\s+\d{1,2}:\d{2}(?:\s*GMT[+-]\d+)?)?")
# 忽略的头部行: "Thứ X, ngày ... tháng ... năm ..."(星期几+越南语年月日)
SKIP_HEADER_RE = re.compile(
    r"\b(?:Thứ\s*(?:[2-7]|hai|ba|tư|năm|sáu|bảy)|Chủ nhật)\s*,?\s*"
    r"ngày\s+\d{1,2}\s+tháng\s+\d{1,2}\s+năm\s+(20[0-2]\d|19[89]\d)", re.I)
SEASON_RE = re.compile(r"\b(19[89]\d|20[0-2]\d)\s*/\s*\d{2}\b")
HAN_RE = re.compile(r"[\u4e00-\u9fff]")
EN_WORD = re.compile(r"\b(the|and|of|with|for|from|this|that)\b", re.I)

LEAK_EXACT = [
    (re.compile(r"Hải Phòng.{0,80}?1\s*-\s*2.{0,80}?Thanh Hóa", re.I | re.S), "M1"),
    (re.compile(r"Thanh Hóa.{0,80}?2\s*-\s*1.{0,80}?Hải Phòng", re.I | re.S), "M1"),
    (re.compile(r"Hà Nội(?!.*Đà Nẵng).{0,80}?1\s*-\s*0.{0,80}?Bắc Ninh", re.I | re.S), "M2"),
    (re.compile(r"luân lưu.{0,60}?4\s*-\s*3", re.I | re.S), "M3"),
    (re.compile(r"Hà Nội.{0,60}?1\s*-\s*1.{0,80}?Đà Nẵng", re.I | re.S), "M3"),
    (re.compile(r"Đồng Nai.{0,80}?4\s*-\s*3.{0,80}?Bình Minh", re.I | re.S), "M4"),
    (re.compile(r"Braga.{0,80}?1\s*-\s*3.{0,80}?Sporting", re.I | re.S), "M5"),
    (re.compile(r"Sporting.{0,80}?3\s*-\s*1.{0,80}?Braga", re.I | re.S), "M5"),
    (re.compile(r"Thể Công.{0,80}?1\s*-\s*3.{0,80}?Hà Tĩnh", re.I | re.S), "G1"),
    (re.compile(r"Hà Tĩnh.{0,80}?3\s*-\s*1.{0,80}?Thể Công", re.I | re.S), "G1"),
]


# ---- 足球实体抽取(比"大写词"更精确:要求尾词是俱乐部/赛事类后缀,或整体是已知赛事) ----
ENT_RE = re.compile(
    r"\b(?:[A-ZÀ-Ỹ][\wÀ-ỹ]*\s+){0,3}"
    r"(?:FC|CLB|United|City|Town|Athletic|Rovers|Wanderers|Sporting|"
    r"Real|Atletico|Internazionale|Juventus|Barcelona|Madrid|Bayern|"
    r"Liverpool|Arsenal|Chelsea|Tottenham|Manchester|Everton|Newcastle|"
    r"Braga|Porto|Benfica|Ajax|PSG|Milan|Roma|Napoli|Dortmund|Leipzig)\b"
    r"|\b(?:Cúp|Giải|V\.?League|Champions League|World Cup|Euro|"
    r"Ngoại hạng Anh|La Liga|Serie A|Bundesliga|Ligue 1|AFF Cup|"
    r"Asian Cup|SEA Games)\b[\wÀ-ỹ\s]{0,20}")
ENT_STOP = {"the", "and", "cúp", "giải", "vòng", "trận", "đội", "bóng đá"}


def norm(t):
    return unicodedata.normalize("NFC", t or "")


def is_football(t):
    return len(FOOTBALL_KW.findall(t)) >= 2


def ctx_hits(t):
    """命中几个**不同**的比赛专属语境词。"""
    return sum(1 for rx in MATCH_CTX_RES if rx.search(t))


CTX_WINDOW = 400   # 语境词必须落在比分的 ±400 字符窗口内


def _ctx_near_scores(t):
    """在比分周围的窗口里统计比赛专属语境词(避免聚合页/长文中
    正文不相关段落里的足球词把文章误判为赛果)。"""
    scores = list(SCORE_RE.finditer(DATE_RE.sub(" ", UNIT_RE.sub(" ", t))))
    if not scores:
        return 0
    win = ""
    for m in scores:
        win += t[max(0, m.start() - CTX_WINDOW): m.end() + CTX_WINDOW] + " \n "
    return sum(1 for rx in MATCH_CTX_RES if rx.search(win))


def is_ket_qua(t):
    """赛果收紧:比分 + 比分附近(±400 字符)≥2 个不同比赛语境词
    + (进球分钟 或 比分动词)。排除其他球类/项目。"""
    if EXCLUDE_SPORT_RE.search(t) or OTHER_SPORT_TEAMS.search(t):
        return False
    if not find_scores(t):
        return False
    if _ctx_near_scores(t) < 2:
        return False
    return bool(MIN_RE.search(t) or GOAL_VERB.search(t))


def extract_year(t):
    """提取发布时间(年)。

    优先级(评审要求):
      1. "dd/mm/yyyy hh:mm GMT+7" 这类**发布时间**格式 → 取**最早**的一个
         (文章正文里常混入其他日期;发布时间通常在开头)
      2. 赛季写法(2023/24)
      3. 孤立年份(兜底)
    同时忽略 "Thứ X, ngày ... tháng ... năm ..." 这类页面头部行。
    """
    cleaned = TOURNAMENT_RE.sub(" ", t)
    head = cleaned[:2000]          # 发布时间前 2000 字符内找
    # 1) 发布时间(dd/mm/yyyy)
    pub = [int(m.group(3)) for m in PUBDATE_RE.finditer(head)
           if 1990 <= int(m.group(3)) <= 2026]
    if pub:
        return min(pub)            # 取最早(正文里后续日期多为引述)
    # 2) 赛季
    se = [int(m.group(1)) for m in SEASON_RE.finditer(cleaned)
          if 1990 <= int(m.group(1)) <= 2026]
    if se:
        return max(se)
    # 3) 孤立年份(排除头部行里的)
    no_head = SKIP_HEADER_RE.sub(" ", cleaned)
    ys = [int(y) for y in re.findall(r"\b(19[89]\d|20[0-2]\d)\b", no_head)
          if 1990 <= int(y) <= 2026]
    return max(ys) if ys else None


def is_leak(t):
    for rx, tag in LEAK_EXACT:
        if rx.search(t):
            return tag
    return None


# ---- MinHash + 标准分段 LSH ----
NUM_PERM = 128
BANDS = 32
ROWS = NUM_PERM // BANDS  # 4


def minhash_sig(toks):
    """返回 128 个最小哈希值(tuple)。"""
    hs = set()
    for i in range(len(toks) - 2):
        g = toks[i] + " " + toks[i + 1] + " " + toks[i + 2]
        hs.add(int(hashlib.md5(g.encode("utf-8", "ignore")).hexdigest()[:8], 16))
    if not hs:
        return ()
    s = sorted(hs)[:NUM_PERM]
    if len(s) < NUM_PERM:  # 短文本补齐(用自身循环)
        s = s + [s[i % len(s)] for i in range(NUM_PERM - len(s))] if s else ()
    return tuple(s)


def lsh_bands(sig):
    """标准分段 LSH:每 ROWS 行一段,返回段的元组。任一段相同 → 同桶。"""
    if not sig or len(sig) < NUM_PERM:
        return ()
    return tuple(tuple(sig[i:i + ROWS]) for i in range(0, NUM_PERM, ROWS))


def jaccard_sig(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def process_file(fp):
    out = {c: [] for c in CATS}
    c = Counter()
    full_paths = []
    try:
        with open(fp, encoding="utf-8", errors="ignore") as f:
            for line in f:
                c["lines"] += 1
                try:
                    d = json.loads(line)
                except Exception:
                    continue
                raw = norm((d.get("title") or "") + " " + (d.get("content") or ""))
                if not is_football(raw):
                    continue
                c["football"] += 1
                leak = is_leak(raw)
                if leak:
                    c["leak_" + leak] += 1
                    continue
                tags = classify(raw)
                if not tags:
                    continue
                hid = d.get("id") or hashlib.md5(
                    raw.encode("utf-8", "ignore")).hexdigest()[:16]
                toks = re.findall(r"\w+", raw.lower())
                sig = minhash_sig(toks)
                rec = {
                    "id": hid,
                    "content_hash": hashlib.sha256(
                        raw.encode("utf-8", "ignore")).hexdigest()[:16],
                    "year": extract_year(raw),
                    "len": len(raw),
                    "tags": tags,
                    "mt_or_copy": bool(HAN_RE.search(raw)) or len(EN_WORD.findall(raw)) >= 3,
                    "sig": list(sig),
                    "head": raw[:300],
                }
                for tg in tags:
                    out[tg].append(rec)
                    c["cls_" + tg] += 1
                # 全文落盘(本地,不进仓库)
                full_paths.append({"id": hid, "tags": tags,
                                   "year": rec["year"], "text": raw})
    except Exception as e:
        c["errors"] += 1
        print(f"  [warn] {fp.name}: {e}", file=sys.stderr)
    return out, c, full_paths


def _worker(args):
    fp, parts_dir, full_dir = args
    name = fp.name
    dest = Path(parts_dir) / (name + ".json")
    fdest = Path(full_dir) / (name + ".jsonl")
    if dest.exists():
        try:
            d = json.loads(dest.read_text(encoding="utf-8"))
            if fdest.exists():
                return name, d, True
        except Exception:
            pass
    out, c, full = process_file(fp)
    payload = {"counters": dict(c), "cats": out}
    dest.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    with fdest.open("w", encoding="utf-8") as f:
        for r in full:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return name, payload, False


def cmd_run(args):
    outdir = ROOT / args.out
    parts = outdir / "parts"
    parts.mkdir(parents=True, exist_ok=True)
    FULLDIR.mkdir(parents=True, exist_ok=True)
    files = sorted(RAW.rglob("*.jsonl"))
    if args.limit_files:
        files = files[:args.limit_files]
    todo = [f for f in files if not (parts / (f.name + ".json")).exists()]
    print(f"分片 {len(files)} 个,待处理 {len(todo)} 个,{args.workers} 进程", flush=True)
    with Pool(args.workers) as pool:
        for i, (name, payload, cached) in enumerate(
                pool.imap_unordered(_worker,
                                    [(f, str(parts), str(FULLDIR)) for f in todo]), 1):
            flag = "(续用)" if cached else ""
            print(f"  [{i}/{len(todo)}] {name} "
                  f"+{payload['counters'].get('football',0)} 足球稿{flag}", flush=True)
    return cmd_status(args)


def cmd_status(args):
    outdir = ROOT / args.out
    parts = outdir / "parts"
    files = sorted(RAW.rglob("*.jsonl"))
    done = list(parts.glob("*.json")) if parts.exists() else []
    allc = Counter()
    for p in done:
        try:
            allc.update(json.loads(p.read_text(encoding="utf-8"))["counters"])
        except Exception:
            pass
    print(f"进度: {len(done)}/{len(files)} 分片")
    print(f"扫描行 {allc['lines']:,},足球稿 {allc['football']:,}")
    for k in sorted(allc):
        print(f"  {k}: {allc[k]:,}")
    return 0


# 足球无关稿(财经/星座/生活等,评审要求剔除)
EF_OFFTOPIC_RE = re.compile(
    r"chòm sao|tử vi|horoscope|cung hoàng đạo|giá vàng|chứng khoán|"
    r"bất động sản|tuyển sinh|thời tiết|nấu ăn|công thức|cách làm|"
    r"khuyến mãi|mua sắm|thời trang|làm đẹp", re.I)


def _ngram_counts(text, n):
    toks = re.findall(r"\w+", text.lower())
    return Counter(" ".join(toks[i:i + n]) for i in range(len(toks) - n + 1))


def cmd_merge(args):
    outdir = ROOT / args.out
    parts = outdir / "parts"
    # 全文按 id 索引(tags 含 ket_qua 的才用于 ngram)
    kq_full, ent_texts, ents = [], [], Counter()
    ent_years = {}   # name -> (first, last)
    year_hist = Counter()
    allc = Counter()
    for p in sorted(parts.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        allc.update(d["counters"])
    # 读全文
    seen_ids = set()
    bad_lines = 0
    for fp in sorted(FULLDIR.glob("*.jsonl")):
        with fp.open(encoding="utf-8", errors="ignore") as fh:
            for line in fh:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    bad_lines += 1
                    continue
                if r["id"] in seen_ids:
                    continue
                seen_ids.add(r["id"])
                y = r.get("year")
                if y:
                    year_hist[y] += 1
                txt = r["text"]
                if "ket_qua" in r["tags"]:
                    kq_full.append((r, txt))
                # 实体抽取:只保留**足球实体**(队名/Cúp 名/赛事名/俱乐部后缀),
                # 不抽普通词。用尾词判定,避免 được/đến 这类句首词。
                for nm in ENT_RE.findall(txt):
                    nm = " ".join(nm.split())
                    if len(nm) < 4:
                        continue
                    low = nm.lower()
                    if low in ENT_STOP:
                        continue
                    ents[nm] += 1
                    if y:
                        if nm not in ent_years:
                            ent_years[nm] = [y, y]
                        else:
                            ent_years[nm][1] = max(ent_years[nm][1], y)
                            ent_years[nm][0] = min(ent_years[nm][0], y)

    # --- ngram 表:宽口径(评审) ---
    # 赛后衍生稿用语与赛果稿基本一致 → 纳入;只剔除:
    #   标签聚合页、足球无关稿、其他运动项目;并剔 2015 年前
    ng = Counter()
    n_used = 0
    for r, txt in kq_full:
        if (r.get("year") or 0) and r["year"] < 2015:
            continue
        if is_aggregator(txt) or OTHER_SPORT_TEAMS.search(txt):
            continue
        if EF_OFFTOPIC_RE.search(txt[:600]):
            continue
        n_used += 1
        for n in (2, 3, 4):
            ng.update(_ngram_counts(txt, n))
    ng5 = {k: v for k, v in ng.items() if v >= 5}
    with (outdir / "ngram_football_ket_qua.tsv").open("w", encoding="utf-8") as f:
        f.write("ngram\tn\tcount\n")
        for k, v in sorted(ng5.items(), key=lambda x: -x[1]):
            f.write(f"{k}\t{len(k.split())}\t{v}\n")

    # --- 名称表:不设闸门,记录首末年份 ---
    with (outdir / "entity_names_football.tsv").open("w", encoding="utf-8") as f:
        f.write("name\tcount\tfirst_year\tlast_year\n")
        for nm, v in sorted(ents.items(), key=lambda x: -x[1]):
            fy, ly = ent_years.get(nm, ("", ""))
            f.write(f"{nm}\t{v}\t{fy}\t{ly}\n")

    summary = {
        "files_total": len(sorted(RAW.rglob("*.jsonl"))),
        "files_done": len(list(parts.glob("*.json"))),
        "lines": allc["lines"], "football": allc["football"],
        "cls_raw": {k[4:]: v for k, v in allc.items() if k.startswith("cls_")},
        "leak": {k[5:]: v for k, v in allc.items() if k.startswith("leak_")},
        "ngram_rows": len(ng5), "ngram_docs": n_used,
        "entity_rows": len(ents),
        "year_hist": dict(sorted(year_hist.items())),
    }
    (outdir / "STATS.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"赛果全文 {n_used} 篇 → ngram 行 {len(ng5)},实体 {len(ents)}")
    print(f"→ {outdir}/ngram_football_ket_qua.tsv, entity_names_football.tsv")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="distill_football")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit-files", type=int, default=0)
    ap.add_argument("--minhash-threshold", type=float, default=0.8)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--merge", action="store_true")
    args = ap.parse_args(argv)
    if args.status:
        return cmd_status(args)
    if args.merge:
        return cmd_merge(args)
    return cmd_run(args)


if __name__ == "__main__":
    sys.exit(main())
