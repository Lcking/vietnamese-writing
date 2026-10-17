// verify_task_html.js — jsdom 真跑页面,验证渲染与交互(v2 美化版)
const fs = require('fs');
const { JSDOM } = require('jsdom');

const file = process.argv[2] || 'human_eval/html/task_01.html';
const html = fs.readFileSync(file, 'utf8');
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true });
const { window } = dom;
const doc = window.document;

let fails = 0;
function check(name, cond, extra) {
  console.log((cond ? 'OK  ' : 'XX  ') + name + (extra !== undefined ? '  ' + extra : ''));
  if (!cond) fails++;
}

setTimeout(() => {
  check('标题含 "Phiếu đánh giá"', /Phiếu đánh giá/.test(doc.title), doc.title);
  check('A 段 2 张卡', doc.querySelectorAll('#A .card').length === 2,
        doc.querySelectorAll('#A .card').length);
  check('B 段 5 张卡', doc.querySelectorAll('#B .card').length === 5,
        doc.querySelectorAll('#B .card').length);
  check('C 段 9 张卡', doc.querySelectorAll('#C .card').length === 9,
        doc.querySelectorAll('#C .card').length);
  check('进度胶囊存在', !!doc.getElementById('pill'));
  check('进度条存在', !!doc.getElementById('bar'));
  check('三个分区标题', doc.querySelectorAll('.sec').length === 3,
        doc.querySelectorAll('.sec').length);

  const chip = doc.querySelector('#A .chip');
  check('有可点 chip', !!chip);
  chip.dispatchEvent(new window.Event('click', { bubbles: true }));
  check('点选加 sel 类', chip.classList.contains('sel'));

  setTimeout(() => {
    const pill = doc.getElementById('pill').textContent;
    check('进度胶囊更新', /Đã làm [1-9]/.test(pill), pill);
    const w = doc.getElementById('bar').style.width;
    check('进度条宽度变化', w && w !== '0%', w);

    const nat = doc.querySelector('[name="a0_nat"]');
    nat.value = '4';
    nat.dispatchEvent(new window.Event('input', { bubbles: true }));
    check('分数计入进度', /Đã làm [2-9]/.test(doc.getElementById('pill').textContent),
          doc.getElementById('pill').textContent);

    // 导出
    window.URL.createObjectURL = () => 'blob:x';
    window.HTMLAnchorElement.prototype.click = function () {};
    let ok = true;
    try { window.exportAll(); }
    catch (e) { ok = false; console.log('   导出异常:', e.message); }
    check('导出不抛异常', ok);
    check('导出后显示完成块', doc.getElementById('done').style.display === 'block');

    check('无占位符残留', !html.includes('__DATA__') && !html.includes('__CSS__'));
    check('无外部资源', !/<(script|link)[^>]+(src|href)="http/.test(html));
    check('CSS 已内联', html.includes('.chip.sel') || html.includes('--acc'));

    console.log('\n' + (fails ? fails + ' 项失败' : '全部通过'));
    process.exit(fails ? 1 : 0);
  }, 60);
}, 120);
