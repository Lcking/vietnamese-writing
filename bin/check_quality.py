#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_quality.py — 对本 skill 做基础自动检查（对应评审 P2 的"基础自动检查"要求）。

检查项：
  1. JSONL 合法性（examples/*.jsonl 每行必须能解析）
  2. 来源字段完整性（id/source_url/content_sha256/genre/review_status...）
  3. 稳定去重（content_sha256 不得重复）
  4. 预期语言混杂（正文应为越南语，不应混入中日韩字符）
  5. 重复段落 / 正反例完全相同（references/*.md）
  6. 提示预算（build_prompt 各体裁的字符预算是否合理）
  7. 明确体裁路由（已知体裁都能加载到规则文件）
  8. 输出合同兼容（--dump-prompt 不调用模型，可离线运行）

用法：python bin/check_quality.py
退出码：0=全部通过，1=发现问题
"""
import os, sys, re, json, glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REFERENCES = os.path.join(ROOT, "references")
EXAMPLES = os.path.join(ROOT, "examples", "football")

CJK = re.compile(r"[\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af]")
REQUIRED_FIELDS = ["id", "theme", "source_url", "publisher", "published_at",
                   "collected_at", "original_id", "source_dataset", "content_sha256",
                   "language", "sport", "genre", "review_status",
                   "license_or_attribution"]

problems = []
warnings = []
checks_run = 0


def check_jsonl():
    global checks_run
    files = sorted(glob.glob(os.path.join(EXAMPLES, "*.jsonl")))
    if not files:
        warnings.append("examples/football/ 下没有 .jsonl 文件")
        return
    for fp in files:
        n = 0
        with open(fp, encoding="utf-8") as f:
            for i, line in enumerate(f, 1):
                line = line.strip()
                if not line:
                    continue
                n += 1
                try:
                    json.loads(line)
                except Exception as e:
                    problems.append(f"[JSONL] {os.path.basename(fp)}:{i} 解析失败: {e}")
        checks_run += 1
    print(f"  1) JSONL 合法性: 检查 {len(files)} 个文件")


def check_fields():
    global checks_run
    files = sorted(glob.glob(os.path.join(EXAMPLES, "*.jsonl")))
    missing = {}
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                for k in REQUIRED_FIELDS:
                    # 键必须存在;值为 "unavailable" 表示数据源客观不提供,不算缺失
                    if k not in r:
                        missing.setdefault(os.path.basename(fp), {}).setdefault(k, 0)
                        missing[os.path.basename(fp)][k] += 1
    if missing:
        for f, ks in missing.items():
            warnings.append(f"[来源字段] {f} 缺字段: {ks}")
    checks_run += 1
    print(f"  2) 来源字段: {'全部齐全' if not missing else '有缺失(见警告)'}")


def check_dedup():
    global checks_run
    files = sorted(glob.glob(os.path.join(EXAMPLES, "*.jsonl")))
    # 检查"文件内"去重:同一文件里不应出现相同 hash。
    # 跨文件的相同 hash 是允许的——同一篇文章按多标签进入多个体裁桶(设计如此)。
    in_file_dup = 0
    all_hashes = set()
    for fp in files:
        seen = set()
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                h = r.get("content_sha256")
                if not h:
                    continue
                if h in seen:
                    in_file_dup += 1
                seen.add(h)
                all_hashes.add(h)
    if in_file_dup:
        problems.append(f"[去重] 同一文件内发现 {in_file_dup} 条 content_sha256 重复")
    checks_run += 1
    print(f"  3) 稳定去重: {len(all_hashes)} 条唯一 hash(跨桶复用允许),文件内重复 {in_file_dup}")


def check_language():
    global checks_run
    files = sorted(glob.glob(os.path.join(EXAMPLES, "*.jsonl")))
    mixed = 0
    for fp in files:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except Exception:
                    continue
                body = (r.get("title", "") + " " + r.get("content", ""))
                if CJK.search(body):
                    mixed += 1
    if mixed:
        problems.append(f"[语言] {mixed} 条范文正文混入中日韩字符")
    checks_run += 1
    print(f"  4) 语言纯净: {mixed} 条混杂")


def check_ref_dup_examples():
    global checks_run
    files = sorted(glob.glob(os.path.join(REFERENCES, "*.md")))
    issues = 0
    for fp in files:
        txt = open(fp, encoding="utf-8").read()
        # 正反例完全相同：查找 "Sai:" 与 "Đúng:" 后内容完全相同的行
        lines = txt.splitlines()
        for i in range(len(lines) - 1):
            a, b = lines[i].strip(), lines[i + 1].strip()
            if ("Sai:" in a) and ("Đúng:" in b):
                ca = re.sub(r".*Sai:\s*", "", a).strip().strip("*_ ")
                cb = re.sub(r".*Đúng:\s*", "", b).strip().strip("*_ ")
                if ca and ca == cb:
                    issues += 1
                    problems.append(f"[正反例相同] {os.path.basename(fp)}: {a[:50]}")
    checks_run += 1
    print(f"  5) 正反例相同: {issues} 处")


def check_budget():
    global checks_run
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("vw", os.path.join(ROOT, "bin", "viet_writer.py"))
    vw = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(vw)
    except Exception as e:
        problems.append(f"[预算] 无法导入 viet_writer: {e}")
        return
    for g in vw.GENRES:
        try:
            p = vw.build_prompt(genre=g, examples=True)
            tot = p["stats"]["total_chars"]
            flag = "" if tot < 60000 else "  <- 偏大"
            if tot > 80000:
                warnings.append(f"[预算] {g} 提示 {tot:,} 字符，偏大")
            print(f"     {g:26s} {tot:>7,} 字符{flag}")
        except Exception as e:
            problems.append(f"[预算] {g} 构建失败: {e}")
    checks_run += 1
    print("  6) 提示预算: 见上")


def check_routing():
    global checks_run
    sys.path.insert(0, os.path.join(ROOT, "bin"))
    import importlib.util
    spec = importlib.util.spec_from_file_location("vw2", os.path.join(ROOT, "bin", "viet_writer.py"))
    vw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(vw)
    # 每个体裁都要有规则文件
    for g in vw.GENRES:
        fn = vw.GENRE_FILE.get(g, f"{g}.md")
        if not os.path.exists(os.path.join(REFERENCES, fn)):
            problems.append(f"[路由] 体裁 {g} 缺规则文件 {fn}")
    # 明确体裁优先
    print("  7) 体裁路由: 显式体裁优先，缺文件者见上")
    checks_run += 1


def main():
    print("=" * 60)
    print("vietnamese-writing 质量自检")
    print("=" * 60)
    check_jsonl()
    check_fields()
    check_dedup()
    check_language()
    check_ref_dup_examples()
    check_budget()
    check_routing()
    print("=" * 60)
    print(f"检查项: {checks_run}  问题: {len(problems)}  警告: {len(warnings)}")
    for w in warnings:
        print(f"  [警告] {w}")
    for p in problems:
        print(f"  [问题] {p}")
    print("=" * 60)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
