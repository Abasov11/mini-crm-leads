const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
import fs from 'fs';
const env = Object.fromEntries(fs.readFileSync('.env','utf8').split('\n').filter(l=>l.includes('=')).map(l=>[l.slice(0,l.indexOf('=')), l.slice(l.indexOf('=')+1)]));
const BASE = 'https://crm.213-32-66-46.nip.io';
const user = process.argv[2] || 'demo';
const pages = (process.argv[3] || '/,/leads/1,/leads/new,/settings').split(',');
const b = await chromium.launch();
for (const [tag, vp, scheme] of [['desk',{width:1440,height:900},'light'],['mob',{width:375,height:812},'light'],['dark',{width:1280,height:800},'dark']]) {
  const ctx = await b.newContext({ viewport: vp, colorScheme: scheme, deviceScaleFactor: 1 });
  const p = await ctx.newPage();
  const errs = []; p.on('console', m => m.type()==='error' && errs.push(m.text())); p.on('pageerror', e => errs.push(String(e)));
  await p.goto(BASE + '/login');
  await p.fill('#u', user); await p.fill('#p', user==='admin'?env.ADMIN_PASSWORD:env.DEMO_PASSWORD);
  await p.click('button.btn-primary'); await p.waitForURL(BASE + '/');
  for (const path of pages) {
    await p.goto(BASE + path); await p.waitForTimeout(400);
    const sw = await p.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    const name = `shots/${tag}${path.replace(/[\/?=&]/g,'_')}.png`;
    await p.screenshot({ path: name, fullPage: true });
    console.log(name, 'hscroll=' + sw);
  }
  if (errs.length) console.log(tag, 'ERRORS', errs);
  await ctx.close();
}
await b.close();
