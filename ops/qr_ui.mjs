// Живая проверка подключения по QR из интерфейса: отключить → подключить → QR → подтвердить → «Подключён»
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
import { execFileSync } from 'child_process';
import fs from 'fs';
const env = Object.fromEntries(fs.readFileSync('.env','utf8').split('\n').filter(l=>l.includes('=')).map(l=>[l.slice(0,l.indexOf('=')), l.slice(l.indexOf('=')+1)]));
const BASE = 'https://crm.213-32-66-46.nip.io';
const b = await chromium.launch(); const p = await (await b.newContext()).newPage();
await p.goto(BASE + '/login'); await p.fill('#u', 'admin'); await p.fill('#p', env.ADMIN_PASSWORD);
await p.click('button.btn-primary'); await p.waitForURL(BASE + '/');
await p.goto(BASE + '/settings');
p.on('dialog', d => d.accept());
if (await p.locator('button:has-text("Отключить")').count()) {
  await p.click('button:has-text("Отключить")'); await p.waitForSelector('text=Аккаунт не подключён');
  console.log('OK   отключён');
}
await p.click('button:has-text("Подключить по QR-коду")');
await p.waitForSelector('.qr svg');
await p.locator('.qr').screenshot({ path: 'shots/qr.png' });
await p.screenshot({ path: 'shots/settings_qr.png', fullPage: true });
console.log('OK   QR показан');
console.log(execFileSync('venv/bin/python', ['ops/qr_accept.py', 'shots/qr.png']).toString().trim());
await p.waitForSelector('text=Подключён', { timeout: 20000 });
console.log('OK   после скана: ' + (await p.locator('.ok-line').innerText()));
await b.close();
