// e2e_v3.js — 真实浏览器完整填表(含星级+多句改稿)→ 导出 → 供解析
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const person = process.argv[2] || '01';
const outDir = '/home/abc/.hermes/workspace/viet_skill_draft/human_eval/returned';

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1000, height: 1000 });
  await page.goto('file://' + path.resolve(`human_eval/html/task_${person}.html`),
                  { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 500));

  await page.evaluate(() => {
    // 所有 chips 选第一项
    document.querySelectorAll('.chips').forEach(box => {
      const c = box.querySelector('.chip');
      if (c) c.click();
    });
    // 所有星级点第 4 颗
    document.querySelectorAll('.stars').forEach(box => {
      const ss = box.querySelectorAll('.star');
      if (ss[3]) ss[3].click();
    });
    // 第一篇文章加两句改稿
    const list = document.querySelector('.fixlist');
    const add = list.nextElementSibling;
    window.addFix(add);
    const its = list.querySelectorAll('.fixitem');
    its[0].querySelector('.fix_bad').value = 'Câu sai số một.';
    its[0].querySelector('.fix_good').value = 'Câu đúng số một.';
    its[1].querySelector('.fix_bad').value = 'Câu sai số hai.';
    its[1].querySelector('.fix_good').value = 'Câu đúng số hai.';
  });
  await new Promise(r => setTimeout(r, 400));

  const st = await page.evaluate(() => ({
    pill: document.getElementById('pill').textContent,
    bar: document.getElementById('bar').style.width,
    ck: ['A','B','C'].map(s => document.getElementById('ck'+s).textContent),
  }));
  console.log('  进度:', st.pill, '| 条宽:', st.bar, '| 分区勾选:', JSON.stringify(st.ck));

  const client = await page.target().createCDPSession();
  await client.send('Page.setDownloadBehavior',
    { behavior: 'allow', downloadPath: outDir });
  await page.click('button.primary');
  await new Promise(r => setTimeout(r, 1500));
  await browser.close();

  const f = path.join(outDir, `ket_qua_nguoi_${person}.json`);
  if (fs.existsSync(f)) {
    const d = JSON.parse(fs.readFileSync(f, 'utf8'));
    console.log('  导出 OK | nat:', d.blind[0].nat, '| fixes:', d.blind[0].fixes.length,
                '|', JSON.stringify(d.blind[0].fixes));
  } else console.log('  XX 未找到导出文件');
})();
