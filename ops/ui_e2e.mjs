// UI-сценарий проверяющего: тег в карточке → фильтр по тегу → ручной лид с тегами → живое появление в списке
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
import fs from 'fs';
const env = Object.fromEntries(fs.readFileSync('.env','utf8').split('\n').filter(l=>l.includes('=')).map(l=>[l.slice(0,l.indexOf('=')), l.slice(l.indexOf('=')+1)]));
const BASE = 'https://crm.213-32-66-46.nip.io';
const ok = (c, m) => { console.log((c ? 'OK  ' : 'FAIL') + ' ' + m); if (!c) process.exitCode = 1; };
const b = await chromium.launch();
async function session() {
  const ctx = await b.newContext({ viewport: { width: 1280, height: 800 } });
  const p = await ctx.newPage();
  p.on('pageerror', e => ok(false, 'pageerror ' + e));
  await p.goto(BASE + '/login'); await p.fill('#u', 'demo'); await p.fill('#p', env.DEMO_PASSWORD);
  await p.click('button.btn-primary'); await p.waitForURL(BASE + '/');
  return p;
}
const p = await session();
// 1. тег в карточке
await p.click('text=Тест Е2Е'); await p.waitForURL(/\/leads\/\d+/);
const leadUrl = p.url();
await p.fill('#tags input[name=name]', 'лендинг'); await p.keyboard.press('Enter');
await p.waitForSelector('#tags .tag:has-text("лендинг")'); ok(true, 'тег добавлен в карточке');
await p.fill('#tags input[name=name]', 'Срочно'); await p.keyboard.press('Enter');
await p.waitForSelector('#tags .tag:has-text("Срочно")');
// статус
await p.selectOption('select[name=status]', 'work'); await p.waitForSelector('#saved:has-text("Сохранено")'); ok(true, 'статус сохранён');
// снять тег
await p.click('#tags .tag:has-text("Срочно") .tag-x');
await p.waitForFunction(() => !document.querySelector('#tags .tag-list')?.textContent.includes('Срочно')); ok(true, 'тег снят');
// 2. фильтр по тегу
await p.goto(BASE + '/');
await p.click('.sidebar >> text=лендинг');
await p.waitForURL(/tag=/);
ok(await p.locator('h1').innerText().then(t => t.includes('#лендинг')), 'заголовок фильтра #лендинг');
ok(await p.locator('tbody tr').count() === 1, 'по тегу виден 1 лид');
// 3. ручной лид
await p.click('a.btn-primary:has-text("Лид")'); await p.waitForURL(/leads\/new/);
await p.fill('#name', 'Ольга (вручную)'); await p.fill('#contact', 'olga@example.com');
await p.fill('#req', 'Позвонила по рекомендации, нужен SMM на 3 месяца');
await p.click('[data-add-tag="лендинг"]');
await p.fill('#tags', (await p.inputValue('#tags')) + ', SMM');
await p.click('button:has-text("Сохранить лида")'); await p.waitForURL(/leads\/\d+$/);
ok(await p.locator('#tags .tag-list .tag').count() === 2, 'ручной лид создан с 2 тегами');
await p.goto(BASE + '/'); await p.click('.sidebar >> text=лендинг'); await p.waitForURL(/tag=/); await p.waitForTimeout(300);
ok(await p.locator('tbody tr').count() === 2, 'по тегу «лендинг» теперь 2 лида');
// 4. живое обновление: второй пользователь добавляет лида, первый видит без перезагрузки
await p.goto(BASE + '/');
await p.waitForTimeout(800);
const p2 = await session();
await p2.goto(BASE + '/leads/new'); await p2.fill('#name', 'Живой тест'); await p2.click('button:has-text("Сохранить лида")');
await p.waitForSelector('tbody tr:has-text("Живой тест")', { timeout: 8000 });
ok(true, 'новый лид появился в открытом списке без перезагрузки');
ok(await p.locator('tbody tr.flash').count() === 1, 'новая строка подсвечена');
ok(!(await p2.content()).includes('Удалить лида'), 'демо не видит кнопку удаления');
await b.close();
