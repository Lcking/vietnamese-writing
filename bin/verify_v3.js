// verify_v3.js — 验证 v3 新交互:星级、多句改稿、侧边栏、导出
const fs = require('fs');
const { JSDOM } = require('jsdom');

const file = process.argv[2] || 'human_eval/html/task_01.html';
const html = fs.readFileSync(file, 'utf8');
const dom = new JSDOM(html, { runScripts: 'dangerously', pretendToBeVisual: true });
const { window } = dom, doc = window.document;
let fails = 0;
const check = (n, c, x) => { console.log((c?'OK  ':'XX  ')+n+(x!==undefined?'  '+x:'')); if(!c) fails++; };

setTimeout(() => {
  // --- 星级 ---
  const starsBox = doc.querySelector('.stars');
  const s4 = starsBox.querySelectorAll('.star')[3];
  s4.dispatchEvent(new window.Event('click', { bubbles: true }));
  check('点第4颗星 → 选中', s4.classList.contains('on'));
  check('前4颗全亮', starsBox.querySelectorAll('.star.on').length === 4,
        starsBox.querySelectorAll('.star.on').length);
  check('分值显示', doc.getElementById('v_'+starsBox.dataset.name).textContent === '4/5',
        doc.getElementById('v_'+starsBox.dataset.name).textContent);
  check('星级计入 DATA 值', starsBox.dataset.val === '4', starsBox.dataset.val);

  // 点低分(2)应切成橙色 low
  chars: {
    const s2 = starsBox.querySelectorAll('.star')[1];
    s2.dispatchEvent(new window.Event('click', { bubbles: true }));
    check('点第2颗 → low 配色', starsBox.querySelector('.star.on').classList.contains('low'));
    // 复位成 4
    s4.dispatchEvent(new window.Event('click', { bubbles: true }));
  }

  // --- 多句改稿 ---
  const list = doc.querySelector('.fixlist');
  check('初始 1 条改稿', list.querySelectorAll('.fixitem').length === 1);
  const addBtn = list.nextElementSibling;
  window.addFix(addBtn);
  window.addFix(addBtn);
  check('点两次"加一句" → 3 条', list.querySelectorAll('.fixitem').length === 3,
        list.querySelectorAll('.fixitem').length);
  check('序号自动 1/2/3', [...list.querySelectorAll('.idx')].map(e=>e.textContent).join(',') === '1,2,3',
        [...list.querySelectorAll('.idx')].map(e=>e.textContent).join(','));
  // 填内容
  const items = list.querySelectorAll('.fixitem');
  items[0].querySelector('.fix_bad').value = 'Câu sai một.';
  items[0].querySelector('.fix_good').value = 'Câu đúng một.';
  items[1].querySelector('.fix_bad').value = 'Câu sai hai.';
  items[1].querySelector('.fix_good').value = 'Câu đúng hai.';
  // 先验证三条都能导出
  const before = window.fixPairs(0);
  check('三条改稿都被读到', before.length === 2, JSON.stringify(before.map(f=>f.sai)));
  // 删中间一条
  window.delFix(items[1].querySelector('.del'));
  check('删一条 → 2 条', list.querySelectorAll('.fixitem').length === 2);
  check('删除后重新编号', [...list.querySelectorAll('.idx')].map(e=>e.textContent).join(',') === '1,2');

  // --- 侧边栏 ---
  check('侧边栏 3 项', doc.querySelectorAll('.sidenav a').length === 3);
  check('锚点存在', !!doc.getElementById('secA') && !!doc.getElementById('secB') && !!doc.getElementById('secC'));
  check('勾选位存在', !!doc.getElementById('ckA'));

  // --- 导出 ---
  window.URL.createObjectURL = () => 'blob:x';
  let captured = null;
  const origBlob = window.Blob;
  window.Blob = function(parts, opts) { captured = parts[0]; return new origBlob(parts, opts); };
  window.HTMLAnchorElement.prototype.click = function () {};
  window.exportAll();
  let data = null;
  try { data = JSON.parse(captured); } catch (e) { check('导出 JSON 可解析', false, e.message); }
  if (data) {
    check('导出 JSON 可解析', true);
    check('blind 有 fixes 数组', Array.isArray(data.blind[0].fixes));
    check('导出的是删除后剩下的一条', data.blind[0].fixes.length === 1 &&
          data.blind[0].fixes[0].sai === 'Câu sai một.',
          JSON.stringify(data.blind[0].fixes));
    check('星级值已导出', data.blind[0].nat === '4', data.blind[0].nat);
    check('C 部分 note 字段', 'note' in data.cands[0]);
  }

  console.log('\n' + (fails ? fails + ' 项失败' : '全部通过'));
  process.exit(fails ? 1 : 0);
}, 700);
