#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_single_task_html.py — 生成 10 份单文件 HTML 任务页(v2,美化版)。

每人一份,含三块任务:
  A. 盲测评分 (2 篇)   —— 4 项打分 + "要改的句子"(核心)
  B. 分类抽查 (5 条)   —— 赛果 / 非赛果
  C. 范文确认 (9 条)   —— 可用 / 不可用

特点:
  - 单文件、离线可用(不依赖网络),手机/电脑都能开
  - CSS 内联(来自 human_eval/html/style.css)
  - 填完点"导出结果"→ 下载 JSON → 发回

输出: human_eval/html/task_01.html ... task_10.html
"""
import csv
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "human_eval" / "html"
N_PEOPLE = 10


def parse_blind():
    p = ROOT / "eval" / "blind_review_20261013" / "phieu_cham_mu.md"
    allt = p.read_text(encoding="utf-8")
    txt = allt.split("# Dữ kiện gốc")[0]
    items = []
    for m in re.finditer(r"## (B\d+) \(trận (G\d+)\)\s*\n\s*\n(.+?)(?=\n---|\Z)",
                         txt, re.S):
        code, game, block = m.group(1), m.group(2), m.group(3).strip()
        lines = [l for l in block.split("\n") if l.strip()]
        items.append({"code": code, "game": game,
                      "title": lines[0].strip(),
                      "body": "\n\n".join(lines[1:]) if len(lines) > 1 else ""})
    facts = {}
    fx = allt.split("# Dữ kiện gốc")[1] if "# Dữ kiện gốc" in allt else ""
    for m in re.finditer(r"## (G\d+)\s*\n\s*\n(.+?)(?=\n## |\Z)", fx, re.S):
        facts[m.group(1)] = m.group(2).strip()
    for it in items:
        it["facts"] = facts.get(it["game"], "")
    return items


def load_csv(path, cols):
    rows = []
    with open(ROOT / path, newline="", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            rows.append({k: r.get(c, "") for k, c in cols.items()})
    return rows


HEAD = """<!DOCTYPE html>
<html lang="vi">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phiếu đánh giá — Người __PERSON__/__TOTAL__</title>
<style>
__CSS__
</style>
</head>
<body>
<header>
  <div class="hbar">
    <div class="brand">
      <div class="logo">V</div>
      <div>
        <h1>Phiếu đánh giá bản tin bóng đá</h1>
        <div class="who">Người __PERSON__ / __TOTAL__</div>
      </div>
    </div>
    <span class="pill" id="pill">Chưa làm</span>
  </div>
  <div class="pbar"><i id="bar"></i></div>
</header>

<div class="wrap">
  <div class="card intro">
    <h2>Cảm ơn bạn đã giúp! 🙏</h2>
    <div class="sub">Có 3 phần, làm lần lượt. Xong thì bấm nút ở cuối trang để tải kết quả.</div>
    <ol class="steps">
      <li><b>Phần A</b> — Chấm 2 bản tin kết quả. <span class="note">Quan trọng nhất: viết lại câu cần sửa.</span></li>
      <li><b>Phần B</b> — 5 tin: có phải bản tin kết quả một trận bóng đá không?</li>
      <li><b>Phần C</b> — 9 bài: có đúng thể loại đã ghi không?</li>
    </ol>
    <p class="note" style="margin:12px 0 0">Không cần đoán bài nào do công cụ nào viết — cứ chấm theo cảm nhận người Việt.</p>
  </div>

  <div class="sec"><span class="n">A</span><h2>Chấm bản tin kết quả</h2>
    <span class="meta">2 bài</span></div>
  <div id="A"></div>

  <div class="sec"><span class="n">B</span><h2>Bài này có phải bản tin kết quả không?</h2>
    <span class="meta">5 tin</span></div>
  <div id="B"></div>

  <div class="sec"><span class="n">C</span><h2>Bài này có đúng thể loại không?</h2>
    <span class="meta">9 bài</span></div>
  <div id="C"></div>

  <div class="export">
    <h2 style="margin:0 0 6px">Xong rồi! Tải kết quả</h2>
    <div class="sub" style="margin-bottom:16px">Bấm nút dưới — một file sẽ được tải về máy.
      Gửi file đó lại cho người phụ trách.</div>
    <button class="primary" onclick="exportAll()">⬇ Tải kết quả (.json)</button>
    <div class="done" id="done"></div>
  </div>
</div>
"""

TAIL = """
<script>
const DATA = __DATA__;
const CATNAME = {ket_qua:"Bản tin kết quả", truoc_tran:"Nhận định trước trận",
                 social:"Bài ngắn / mạng xã hội"};

function esc(s) { return (s||"").replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
function chips(name, opts, cls) {
  return '<div class="chips" data-name="'+name+'">' + opts.map(o =>
    '<div class="chip '+(cls||'')+'" data-v="'+o.v+'" onclick="pick(this)">'+o.t+'</div>').join('') + '</div>';
}
function pick(el) {
  el.parentNode.querySelectorAll('.chip').forEach(c => c.classList.remove('sel'));
  el.classList.add('sel');
  updateProgress();
}
function val(name) {
  const b = document.querySelector('.chips[data-name="'+name+'"] .chip.sel');
  return b ? b.dataset.v : "";
}
function fld(name) { const e = document.querySelector('[name="'+name+'"]'); return e ? e.value : ""; }

function renderA() {
  const h = document.getElementById('A');
  DATA.blind.forEach((it, i) => {
    h.insertAdjacentHTML('beforeend', `
    <div class="card">
      <h2>Bài ${i+1} / 2<span class="tag">${it.code}</span></h2>
      <div class="sub">Đọc bài rồi chấm 4 tiêu chí. Dữ kiện gốc ở khung vàng bên dưới.</div>
      <div class="art">
        <div class="tt">${esc(it.title)}</div>
        <div class="bd">${esc(it.body)}</div>
      </div>
      <div class="facts"><b>Dữ kiện gốc — chỉ những điều này là đúng:</b>
${esc(it.facts)}</div>

      <div class="q">
        <div class="lab"><span class="num">1</span>Đúng sự thật
          <span class="hint">có sai / bịa chi tiết không?</span></div>
        ${chips('a'+i+'_fact', [
          {v:"2", t:"2 · Không sai, không bịa"},
          {v:"1", t:"1 · Có chi tiết thừa"},
          {v:"0", t:"0 · Có sai sự thật"}])}
      </div>

      <div class="q">
        <div class="lab"><span class="num">2</span>Tự nhiên
          <span class="hint">đọc như người Việt viết?</span></div>
        <div class="numscore">
          <input type="number" name="a${i}_nat" min="1" max="5" step="1"
                 oninput="updateProgress()" placeholder="?">
          <div class="scale"><span class="lbl">1 máy móc</span>
            <span class="d"></span><span class="d"></span><span class="d"></span>
            <span class="d"></span><span class="d"></span>
            <span class="lbl">5 tự nhiên</span></div>
        </div>
      </div>

      <div class="q">
        <div class="lab"><span class="num">3</span>Đúng chuẩn báo chí
          <span class="hint">động từ tỷ số, cách ghi tỷ số, tiêu đề</span></div>
        <div class="numscore">
          <input type="number" name="a${i}_std" min="1" max="5" step="1"
                 oninput="updateProgress()" placeholder="?">
          <div class="scale"><span class="lbl">1 sai nhiều</span>
            <span class="d"></span><span class="d"></span><span class="d"></span>
            <span class="d"></span><span class="d"></span>
            <span class="lbl">5 chuẩn</span></div>
        </div>
      </div>

      <div class="q">
        <div class="lab"><span class="num">4</span>Có thể đăng không?</div>
        ${chips('a'+i+'_pub', [
          {v:"co", t:"Có thể đăng ngay"},
          {v:"sua_nho", t:"Sửa chút là được"},
          {v:"khong", t:"Không đăng được"}])}
      </div>

      <div class="q key">
        <div class="lab"><span class="num">✎</span>Câu cần sửa
          <span class="hint">quan trọng nhất!</span></div>
        <div class="hint2">Chép nguyên câu chưa ổn, rồi viết lại cho đúng.
          Nếu bài không có gì cần sửa, để trống.</div>
        <textarea name="a${i}_fix" placeholder="Câu chưa ổn: ...&#10;Câu nên viết: ..."></textarea>
      </div>

      <div class="q">
        <div class="lab"><span class="num">+</span>Ghi chú thêm
          <span class="hint">không bắt buộc</span></div>
        <textarea name="a${i}_note" style="min-height:52px"></textarea>
      </div>
    </div>`);
  });
}

function renderB() {
  const h = document.getElementById('B');
  DATA.audit.forEach((it, i) => {
    h.insertAdjacentHTML('beforeend', `
    <div class="card">
      <h2>Tin ${i+1} / 5<span class="tag">${it.id.slice(0,8)}</span></h2>
      <div class="sub">Đây có phải BẢN TIN KẾT QUẢ một trận bóng đá không?
        <b>Có</b> = tường thuật kết quả một trận cụ thể.
        <b>Không</b> = chuyển nhượng, nhận định, chân dung, danh sách, tin chấn thương,
        môn khác, hoặc chỉ nhắc tỷ số làm ví dụ.</div>
      <div class="art"><div class="bd">${esc(it.head)}</div></div>
      <div class="q">
        <div class="lab"><span class="num">?</span>Câu trả lời</div>
        ${chips('b'+i, [{v:"co",t:"Có",cls:"ok"},{v:"khong",t:"Không",cls:"no"}])}
      </div>
    </div>`);
  });
}

function renderC() {
  const h = document.getElementById('C');
  DATA.cands.forEach((it, i) => {
    h.insertAdjacentHTML('beforeend', `
    <div class="card">
      <h2>Bài ${i+1} / 9<span class="tag cat">${CATNAME[it.cat]||it.cat}</span></h2>
      <div class="sub">Thể loại cần kiểm tra: <b>${CATNAME[it.cat]||it.cat}</b>.
        Bài này có đúng thể loại đó không?</div>
      <div class="art"><div class="bd">${esc(it.head)}</div></div>
      <div class="q">
        <div class="lab"><span class="num">?</span>Kết luận</div>
        ${chips('c'+i, [{v:"ok",t:"Dùng được",cls:"ok"},{v:"no",t:"Không dùng",cls:"no"}])}
      </div>
      <div class="q">
        <div class="lab"><span class="num">+</span>Ghi chú
          <span class="hint">không bắt buộc</span></div>
        <input type="text" name="c${i}_note">
      </div>
    </div>`);
  });
}

function updateProgress() {
  const need = DATA.blind.length*4 + DATA.audit.length + DATA.cands.length;
  let got = 0;
  for (let i=0;i<DATA.blind.length;i++)
    got += (val('a'+i+'_fact')?1:0) + (fld('a'+i+'_nat')?1:0)
         + (fld('a'+i+'_std')?1:0) + (val('a'+i+'_pub')?1:0);
  for (let i=0;i<DATA.audit.length;i++) got += val('b'+i)?1:0;
  for (let i=0;i<DATA.cands.length;i++) got += val('c'+i)?1:0;
  const pct = Math.round(got/need*100);
  document.getElementById('bar').style.width = pct + '%';
  const p = document.getElementById('pill');
  p.textContent = got >= need ? 'Đã xong ✓' : ('Đã làm ' + got + '/' + need);
  if (got >= need) { p.classList.add('done'); document.getElementById('bar').style.width='100%'; }
}

function exportAll() {
  const out = {person: DATA.person, blind:[], audit:[], cands:[]};
  DATA.blind.forEach((it,i)=>out.blind.push({code:it.code, game:it.game,
    fact:val('a'+i+'_fact'), nat:fld('a'+i+'_nat'), std:fld('a'+i+'_std'),
    pub:val('a'+i+'_pub'), fix:fld('a'+i+'_fix'), note:fld('a'+i+'_note')}));
  DATA.audit.forEach((it,i)=>out.audit.push({id:it.id, answer:val('b'+i)}));
  DATA.cands.forEach((it,i)=>out.cands.push({id:it.id, cat:it.cat,
    answer:val('c'+i), note:fld('c'+i+'_note')}));
  const blob = new Blob([JSON.stringify(out,null,2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'ket_qua_nguoi_' + String(DATA.person).padStart(2,'0') + '.json';
  a.click();
  const d = document.getElementById('done');
  d.style.display = 'block';
  d.innerHTML = '✓ Đã tải file <b>ket_qua_nguoi_' +
    String(DATA.person).padStart(2,'0') + '.json</b>. Hãy gửi file này cho người phụ trách. Cảm ơn bạn!';
}

renderA(); renderB(); renderC(); updateProgress();
</script>
</body>
</html>
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    css = (OUT / "style.css").read_text(encoding="utf-8")
    blind = parse_blind()
    audit = load_csv("distill_football/review_ket_qua_50.csv",
                     {"id": "ID", "head": "正文前300字符", "year": "年份"})
    cands = load_csv("distill_football/review_candidates_90.csv",
                     {"id": "ID", "head": "正文前300字符", "cat": "类别", "year": "年份"})
    print(f"盲测稿 {len(blind)} / 抽查 {len(audit)} / 范文 {len(cands)}")

    def take(items, per, person):
        start = ((person - 1) * per) % len(items)
        return [items[(start + k) % len(items)] for k in range(per)]

    by_cat = {}
    for c in cands:
        by_cat.setdefault(c["cat"], []).append(c)

    def take_cands(person):
        out = []
        for cat in ["ket_qua", "truoc_tran", "social"]:
            pool = by_cat.get(cat, [])
            if not pool:
                continue
            start = ((person - 1) * 3) % len(pool)
            out += [pool[(start + k) % len(pool)] for k in range(3)]
        return out

    head = HEAD.replace("__CSS__", css)
    for p in range(1, N_PEOPLE + 1):
        data = {"person": p, "total": N_PEOPLE, "blind": take(blind, 2, p),
                "audit": take(audit, 5, p), "cands": take_cands(p)}
        html = (head.replace("__PERSON__", str(p)).replace("__TOTAL__", str(N_PEOPLE))
                + TAIL.replace("__DATA__", json.dumps(data, ensure_ascii=False)))
        (OUT / f"task_{p:02d}.html").write_text(html, encoding="utf-8")
    print(f"→ {OUT}/  ({N_PEOPLE} 份)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
