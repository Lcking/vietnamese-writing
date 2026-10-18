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

<div class="sidenav" id="sidenav">
  <a href="#secA" data-sec="A"><span class="b">A</span>Chấm bản tin<span class="ck" id="ckA"></span></a>
  <a href="#secB" data-sec="B"><span class="b">B</span>Phân loại tin<span class="ck" id="ckB"></span></a>
  <a href="#secC" data-sec="C"><span class="b">C</span>Xác nhận thể loại<span class="ck" id="ckC"></span></a>
</div>

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

  <div class="sec" id="secA"><span class="n">A</span><h2>Chấm bản tin kết quả</h2>
    <span class="meta">2 bài</span></div>
  <div id="A"></div>

  <div class="sec" id="secB"><span class="n">B</span><h2>Bài này có phải bản tin kết quả không?</h2>
    <span class="meta">5 tin</span></div>
  <div id="B"></div>

  <div class="sec" id="secC"><span class="n">C</span><h2>Bài này có đúng thể loại không?</h2>
    <span class="meta">9 bài</span></div>
  <div id="C"></div>

  <div class="export">
    <h2 style="margin:0 0 6px">Xong rồi! Tải kết quả</h2>
    <div class="sub" style="margin-bottom:14px">Điền tên của bạn (để người phụ trách biết file của ai),
      rồi bấm nút tải về. Gửi file đó lại cho người phụ trách.</div>
    <div style="max-width:420px;margin:0 auto 16px;text-align:left">
      <label style="display:block;font-size:13px;font-weight:650;color:#4a5666;margin-bottom:6px">
        Tên của bạn <span style="color:#c8382f">*</span>
        <span style="font-weight:400;color:#7c8899">(ví dụ: Nguyen Van A)</span></label>
      <input type="text" id="whoName" placeholder="Nhập họ tên của bạn…"
             oninput="updateProgress()"
             style="width:100%;border:1.5px solid #d5dce7;border-radius:10px;padding:11px 13px;font:inherit">
    </div>
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

function stars(name, label1, label5) {
  let h = '<div class="stars" data-name="'+name+'">';
  for (let v=1; v<=5; v++) h += '<div class="star" data-v="'+v+
    '" onclick="setStar(this)">'+v+'</div>';
  h += '</div><span class="scoreval" id="v_'+name+'">chưa chọn</span>';
  return '<div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">' +
    h + '</div><div style="display:flex;gap:6px;margin-top:7px;font-size:12px;color:#7c8899">' +
    '<span style="min-width:76px">'+label1+'</span>' +
    '<span style="flex:1;height:2px;background:linear-gradient(90deg,#e4e9f0,#c9d3e3,#b6c4d8);border-radius:2px;max-width:190px"></span>' +
    '<span>'+label5+'</span></div>';
}
function setStar(el) {
  const box = el.parentNode;
  const v = +el.dataset.v;
  box.dataset.val = v;
  box.querySelectorAll('.star').forEach(s => {
    const sv = +s.dataset.v;
    s.classList.toggle('on', sv <= v);
    s.classList.remove('low','mid','high');
    if (sv <= v) s.classList.add(v <= 2 ? 'low' : (v === 3 ? 'mid' : 'high'));
  });
  const out = document.getElementById('v_' + box.dataset.name);
  if (out) out.textContent = v + '/5';
  updateProgress();
}
function starVal(name) {
  const b = document.querySelector('.stars[data-name="'+name+'"]');
  return b && b.dataset.val ? b.dataset.val : "";
}

/* 改稿条目:一对输入框(原句 / 正确写法),可增删 */
function fixItem(bi, idx) {
  return `<div class="fixitem" data-bi="${bi}">
    <div class="hdr"><span class="idx">${idx}</span>
      <span class="t">Câu số ${idx}</span>
      <button type="button" class="del" onclick="delFix(this)">✕ Xóa</button></div>
    <div class="pair">
      <div class="col bad"><label>Câu viết chưa ổn</label>
        <textarea class="fix_bad" placeholder="Dán nguyên câu trong bài…"></textarea></div>
      <div class="col good"><label>Câu nên viết lại</label>
        <textarea class="fix_good" placeholder="Viết lại cho đúng / tự nhiên hơn…"></textarea></div>
    </div>
  </div>`;
}
function addFix(btn) {
  const list = btn.previousElementSibling;
  const bi = list.dataset.bi;
  const n = list.querySelectorAll('.fixitem').length + 1;
  if (n > 6) { alert('Tối đa 6 câu cho mỗi bài.'); return; }
  list.insertAdjacentHTML('beforeend', fixItem(bi, n));
  updateProgress();
}
function delFix(btn) {
  const list = btn.closest('.fixlist');
  btn.closest('.fixitem').remove();
  // 重新编号
  list.querySelectorAll('.fixitem').forEach((it, i) => {
    it.querySelector('.idx').textContent = i + 1;
    it.querySelector('.t').textContent = 'Câu số ' + (i + 1);
  });
  updateProgress();
}
function fixPairs(bi) {
  const list = document.querySelector('.fixlist[data-bi="'+bi+'"]');
  if (!list) return [];
  const out = [];
  list.querySelectorAll('.fixitem').forEach(it => {
    const bad = it.querySelector('.fix_bad').value.trim();
    const good = it.querySelector('.fix_good').value.trim();
    if (bad || good) out.push({sai: bad, dung: good});
  });
  return out;
}

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
        ${stars('a'+i+'_nat', '1 · máy móc', '5 · tự nhiên')}
      </div>

      <div class="q">
        <div class="lab"><span class="num">3</span>Đúng chuẩn báo chí
          <span class="hint">động từ tỷ số, cách ghi tỷ số, tiêu đề</span></div>
        ${stars('a'+i+'_std', '1 · sai nhiều', '5 · chuẩn')}
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
        <div class="hint2">Mỗi câu chưa ổn: dán nguyên câu vào ô trái, viết lại cho đúng ở ô phải.
          Có nhiều câu thì bấm "Thêm câu". Bài không có gì phải sửa thì để trống.</div>
        <div class="fixlist" data-bi="${i}">
          ${fixItem(i, 1)}
        </div>
        <div class="addfix" onclick="addFix(this)">＋ Thêm câu cần sửa</div>
      </div>

      <div class="q">
        <div class="lab"><span class="num">+</span>Ghi chú thêm
          <span class="hint">không bắt buộc — ví dụ: cả bài nhìn chung thế nào</span></div>
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
  const guide = {
    ket_qua: 'Bản tin kết quả một trận cụ thể: có tỷ số, có diễn biến bàn thắng, đội thắng/thua rõ.',
    truoc_tran: 'Nhận định / dự đoán TRƯỚC khi trận đấu diễn ra: đội hình dự kiến, phong độ, đối đầu, ai sẽ thắng.',
    social: 'Bài ngắn kiểu mạng xã hội / tin nhanh: vài câu, giọng khẩu ngữ, có thể có emoji hoặc dấu chấm than.'
  };
  DATA.cands.forEach((it, i) => {
    h.insertAdjacentHTML('beforeend', `
    <div class="card">
      <h2>Bài ${i+1} / 9<span class="tag cat">${CATNAME[it.cat]||it.cat}</span></h2>
      <div class="sub"><b>Thể loại cần kiểm tra: ${CATNAME[it.cat]||it.cat}</b><br>
        ${guide[it.cat]||''}</div>
      <div class="art"><div class="bd">${esc(it.head)}</div></div>
      <div class="q">
        <div class="lab"><span class="num">?</span>Bài này có đúng thể loại trên không?</div>
        ${chips('c'+i, [{v:"ok",t:"Đúng thể loại — dùng được",cls:"ok"},
                        {v:"no",t:"Sai thể loại — không dùng",cls:"no"}])}
      </div>
      <div class="q">
        <div class="lab"><span class="num">+</span>Nếu sai thể loại, bài này thực ra là gì?
          <span class="hint">không bắt buộc</span></div>
        <input type="text" name="c${i}_note"
               placeholder="Ví dụ: đây là tin chuyển nhượng / chân dung cầu thủ / tin chấn thương…">
      </div>
    </div>`);
  });
}

function updateProgress() {
  const need = DATA.blind.length*4 + DATA.audit.length + DATA.cands.length;
  let got = 0;
  const perSec = {A:[0,0], B:[0,0], C:[0,0]};
  for (let i=0;i<DATA.blind.length;i++) {
    let n = 0;
    n += starVal('a'+i+'_nat')?1:0;
    n += starVal('a'+i+'_std')?1:0;
    n += val('a'+i+'_fact')?1:0;
    n += val('a'+i+'_pub')?1:0;
    got += n; perSec.A[0] += n; perSec.A[1] += 4;
  }
  for (let i=0;i<DATA.audit.length;i++) {
    const k = val('b'+i)?1:0; got += k; perSec.B[0] += k; perSec.B[1] += 1;
  }
  for (let i=0;i<DATA.cands.length;i++) {
    const k = val('c'+i)?1:0; got += k; perSec.C[0] += k; perSec.C[1] += 1;
  }
  const pct = Math.round(got/need*100);
  document.getElementById('bar').style.width = pct + '%';
  const p = document.getElementById('pill');
  const nameEl = document.getElementById('whoName');
  const hasName = nameEl && nameEl.value.trim();
  if (got >= need && hasName) {
    p.textContent = 'Đã xong ✓'; p.classList.add('done');
    document.getElementById('bar').style.width = '100%';
  } else if (got >= need && !hasName) {
    p.textContent = 'Xong phần chấm — nhớ điền tên ở cuối trang';
    p.classList.remove('done');
  } else {
    p.textContent = 'Đã làm ' + got + '/' + need;
    p.classList.remove('done');
  }
  // 侧边栏勾选
  ['A','B','C'].forEach(s => {
    const el = document.getElementById('ck'+s);
    if (el) el.textContent = (perSec[s][0] >= perSec[s][1]) ? '✓' : '';
  });
}

/* 名称转 ASCII(去声调)——保证跨系统/邮件附件不乱码;原名仍存在 JSON 里 */
const VI_MAP = {'à':'a','á':'a','ả':'a','ã':'a','ạ':'a','ă':'a','ằ':'a','ắ':'a','ẳ':'a','ẵ':'a','ặ':'a',
  'â':'a','ầ':'a','ấ':'a','ẩ':'a','ẫ':'a','ậ':'a','đ':'d','è':'e','é':'e','ẻ':'e','ẽ':'e','ẹ':'e',
  'ê':'e','ề':'e','ế':'e','ể':'e','ễ':'e','ệ':'e','ì':'i','í':'i','ỉ':'i','ĩ':'i','ị':'i',
  'ò':'o','ó':'o','ỏ':'o','õ':'o','ọ':'o','ô':'o','ồ':'o','ố':'o','ổ':'o','ỗ':'o','ộ':'o',
  'ơ':'o','ờ':'o','ớ':'o','ở':'o','ỡ':'o','ợ':'o','ù':'u','ú':'u','ủ':'u','ũ':'u','ụ':'u',
  'ư':'u','ừ':'u','ứ':'u','ử':'u','ữ':'u','ự':'u','ỳ':'y','ý':'y','ỷ':'y','ỹ':'y','ỵ':'y'};
function toAscii(s) {
  return (s || '').toLowerCase().split('').map(ch => VI_MAP[ch] || ch).join('')
    .normalize('NFD').replace(/[\u0300-\u036f]/g, '');
}

/* 姓名 → 文件名安全段 */
function slugName(s) {
  const a = toAscii(s).trim().replace(/\s+/g, '-').replace(/[^a-z0-9\-]/g, '');
  return a.replace(/-+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || '';
}

function exportAll() {
  const nameEl = document.getElementById('whoName');
  const rawName = nameEl ? nameEl.value.trim() : '';
  if (!rawName) {
    alert('Vui lòng điền tên của bạn trước khi tải kết quả.');
    if (nameEl) nameEl.focus();
    return;
  }
  const person = String(DATA.person).padStart(2, '0');
  const out = {person: DATA.person, person_code: person, ho_ten: rawName,
               blind:[], audit:[], cands:[]};
  DATA.blind.forEach((it,i)=>{
    const pairs = fixPairs(i);
    out.blind.push({code:it.code, game:it.game,
      fact:val('a'+i+'_fact'), nat:starVal('a'+i+'_nat'), std:starVal('a'+i+'_std'),
      pub:val('a'+i+'_pub'), fixes:pairs,
      fix:(pairs[0] ? (pairs[0].sai + ' → ' + pairs[0].dung) : ''),
      note:fld('a'+i+'_note')});
  });
  DATA.audit.forEach((it,i)=>out.audit.push({id:it.id, answer:val('b'+i)}));
  DATA.cands.forEach((it,i)=>out.cands.push({id:it.id, cat:it.cat,
    answer:val('c'+i), note:fld('c'+i+'_note')}));

  // 文件名: ket_qua_<编号>_<姓名>.json
  const fname = 'ket_qua_' + person + '_' + slugName(rawName) + '.json';
  const blob = new Blob([JSON.stringify(out,null,2)], {type:'application/json'});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = fname;
  a.click();
  const d = document.getElementById('done');
  d.style.display = 'block';
  d.innerHTML = '✓ Đã tải file <b>' + fname + '</b>.<br>' +
    'Hãy gửi file này cho người phụ trách. Cảm ơn bạn!';
}

/* 侧边栏:滚动时高亮当前分区 */
function initNav() {
  const nav = document.querySelectorAll('.sidenav a');
  if (!nav.length) return;
  const secs = ['secA','secB','secC'].map(id => document.getElementById(id));
  const io = new IntersectionObserver(entries => {
    entries.forEach(e => {
      if (e.isIntersecting) {
        nav.forEach(a => a.classList.toggle('act', a.dataset.sec ===
          e.target.id.replace('sec','')));
      }
    });
  }, { rootMargin: '-45% 0px -45% 0px' });
  secs.forEach(s => s && io.observe(s));
}

renderA(); renderB(); renderC(); updateProgress(); initNav();
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
