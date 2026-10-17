// shot.js — 用真实 Chromium 截图,检查视觉效果
const puppeteer = require('puppeteer-core');
const path = process.argv[2] || 'human_eval/html/task_01.html';
const out = process.argv[3] || '/home/abc/.hermes/workspace/viet_skill_draft/human_eval/shot.png';
const full = process.argv[4] === 'full';

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-dev-shm-usage', '--font-render-hinting=none'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 900, height: 1400, deviceScaleFactor: 1.5 });
  await page.goto('file://' + require('path').resolve(path), { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 600));
  await page.screenshot({ path: out, fullPage: full });
  // 顺手抓一段正文文本,确认越南语渲染
  const t = await page.evaluate(() => {
    const el = document.querySelector('#A .art .tt');
    const f = document.querySelector('#A .facts');
    return { title: el ? el.textContent.slice(0, 60) : null,
             hasFacts: !!(f && f.textContent.length > 20),
             cards: document.querySelectorAll('.card').length };
  });
  console.log(JSON.stringify(t, null, 2));
  await browser.close();
})();
