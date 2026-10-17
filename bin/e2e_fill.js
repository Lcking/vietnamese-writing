// e2e_fill.js — 用真实浏览器完整走一遍"同事填表→导出JSON"
// 目的:验证从页面到 JSON 的链路,不依赖人手动测试
const puppeteer = require('puppeteer-core');
const path = require('path');
const fs = require('fs');

const person = process.argv[2] || '01';
const outDir = process.argv[3] || '/home/abc/.hermes/workspace/viet_skill_draft/human_eval/returned';

(async () => {
  fs.mkdirSync(outDir, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 900, height: 1000 });
  await page.goto('file://' + path.resolve(`human_eval/html/task_${person}.html`),
                  { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 400));

  // 模拟填写:每个 chips 组选第一个、每个数字框填 4
  await page.evaluate(() => {
    document.querySelectorAll('.chips').forEach(box => {
      const c = box.querySelector('.chip');
      if (c) { box.querySelectorAll('.chip').forEach(x=>x.classList.remove('sel'));
               c.classList.add('sel'); }
    });
    document.querySelectorAll('input[type=number]').forEach(e => { e.value = '4'; });
    // 给第一篇写一条"改稿"
    const ta = document.querySelector('textarea[name="a0_fix"]');
    if (ta) ta.value = 'Câu chưa ổn: A làm chủ thế đoạn đầu.\nCâu nên viết: A kiểm soát thế trận trong những phút đầu.';
    if (window.updateProgress) window.updateProgress();
  });
  await new Promise(r => setTimeout(r, 300));

  const prog = await page.evaluate(() => document.getElementById('pill').textContent);
  console.log('  进度:', prog);

  // 拦截下载
  const client = await page.target().createCDPSession();
  await client.send('Page.setDownloadBehavior',
    { behavior: 'allow', downloadPath: outDir });

  await page.click('button.primary');
  await new Promise(r => setTimeout(r, 1500));
  await browser.close();

  const f = path.join(outDir, `ket_qua_nguoi_${person}.json`);
  console.log(fs.existsSync(f) ? '  导出成功: ' + f : '  XX 未找到导出文件');
})();
