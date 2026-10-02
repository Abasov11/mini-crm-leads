const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const b = await chromium.launch();
for (const [n, vp] of [['doc_desk', {width:1280,height:900}], ['doc_mob', {width:375,height:812}]]) {
  const p = await (await b.newContext({ viewport: vp })).newPage();
  await p.goto('https://crm.213-32-66-46.nip.io/doc');
  console.log(n, await p.evaluate(() => document.documentElement.scrollWidth - innerWidth));
  await p.screenshot({ path: `shots/${n}.png`, fullPage: true });
}
const p = await (await b.newContext()).newPage();
await p.goto('https://crm.213-32-66-46.nip.io/doc');
await p.pdf({ path: 'Мини-CRM_набросок_и_разбор.pdf', format: 'A4', margin: { top: '14mm', bottom: '14mm', left: '12mm', right: '12mm' }, printBackground: true });
await b.close();
