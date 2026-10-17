// inspect_style.js — 用真实浏览器读取渲染后的样式值,验证视觉设计生效
const puppeteer = require('puppeteer-core');
const path = require('path');

(async () => {
  const browser = await puppeteer.launch({
    executablePath: '/usr/bin/google-chrome',
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 900, height: 1200 });
  await page.goto('file://' + path.resolve('human_eval/html/task_01.html'),
                  { waitUntil: 'load' });
  await new Promise(r => setTimeout(r, 400));

  const info = await page.evaluate(() => {
    const cs = (sel, prop) => {
      const el = document.querySelector(sel);
      return el ? getComputedStyle(el)[prop] : null;
    };
    const rect = (sel) => {
      const el = document.querySelector(sel);
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return { w: Math.round(r.width), h: Math.round(r.height) };
    };
    return {
      header_bg: cs('header', 'backgroundColor'),
      header_sticky: cs('header', 'position'),
      logo_gradient: cs('.logo', 'backgroundImage').slice(0, 60),
      sec_gradient: cs('.sec', 'backgroundImage').slice(0, 60),
      card_radius: cs('.card', 'borderRadius'),
      card_shadow: cs('.card', 'boxShadow').slice(0, 50),
      chip_radius: cs('.chip', 'borderRadius'),
      chip_border: cs('.chip', 'borderWidth'),
      key_block_bg: cs('.key', 'backgroundImage').slice(0, 50),
      facts_borderleft: cs('.facts', 'borderLeftWidth') + ' ' + cs('.facts', 'borderLeftColor'),
      art_bg: cs('.art', 'backgroundColor'),
      btn_bg: cs('button.primary', 'backgroundImage').slice(0, 55),
      btn_radius: cs('button.primary', 'borderRadius'),
      pbar_exists: !!document.querySelector('.pbar > i'),
      // 布局宽度
      card_w: rect('.card') && rect('.card').w,
      chip_count: document.querySelectorAll('.chip').length,
      input_count: document.querySelectorAll('input[type=number]').length,
      textarea_count: document.querySelectorAll('textarea').length,
      // 检查是否有横向溢出
      overflowX: document.documentElement.scrollWidth > window.innerWidth,
    };
  });
  console.log(JSON.stringify(info, null, 2));
  await browser.close();
})();
