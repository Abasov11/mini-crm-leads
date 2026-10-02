const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const b = await chromium.launch(); const p = await (await b.newContext({ deviceScaleFactor: 2 })).newPage();
await p.goto(new URL('prompts.html', import.meta.url).href);
for (const id of ['rules', 'review']) await p.locator('#' + id).screenshot({ path: `app/static/doc/prompt_${id}.png` });
await b.close();
