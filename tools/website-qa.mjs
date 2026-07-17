import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const OUT = path.join(ROOT, 'qa-output');
const DEV = process.argv.includes('--dev');
const baseAt = process.argv.indexOf('--base');
const REMOTE = baseAt >= 0 ? process.argv[baseAt + 1]?.replace(/\/$/, '') : null;
const ORIGIN = REMOTE || 'http://127.0.0.1:8766';
const BASE = REMOTE ? `${REMOTE}/` : DEV ? `${ORIGIN}/OpenPharmaStability.dc.html` : `${ORIGIN}/`;
const NAV_URL = REMOTE ? `${BASE}?qa=${Date.now()}` : BASE;
fs.mkdirSync(OUT, { recursive: true });

const result = { screenshots: [], checks: [], errors: [] };
const check = (name, ok, detail = '') => {
  result.checks.push({ name, ok, detail });
  if (!ok) result.errors.push(`${name}: ${detail}`);
};

async function ready(page) {
  await page.waitForFunction(() => window.__dcBoot && document.querySelector('#dc-root'), { timeout: 30000 });
  await page.waitForFunction(() => !document.querySelector('.sc-logic-error'), { timeout: 30000 });
  await page.waitForTimeout(500);
}

async function screenshot(page, name, fullPage = true) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage });
  result.screenshots.push(file);
}

async function inspect(page, label) {
  const state = await page.evaluate(() => ({
    overflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    h1: document.querySelector('h1')?.textContent?.trim(),
    landmarks: ['header', 'nav', 'main', 'footer'].every((tag) => document.querySelector(tag)),
    logicError: document.querySelector('.sc-logic-error')?.textContent || '',
  }));
  check(`${label} no horizontal overflow`, state.overflow <= 1, `overflow=${state.overflow}`);
  check(`${label} semantic landmarks`, state.landmarks);
  check(`${label} correct headline`, state.h1 === 'A reproducible shelf-life decision, with the model record attached.', state.h1);
  check(`${label} no component error`, !state.logicError, state.logicError);
}

async function verifyCopyAndAssets(page) {
  const text = await page.locator('body').innerText();
  const required = [
    '42 rows, 3 batches, 7 time points', 'Slope interaction p=0.9056',
    'common slope + batch intercepts', '17.954842 months', 'Governing batch',
    'impurity_a limits the product decision at 7 months', 'does not depend on extrapolation'
  ];
  const forbidden = ['Hiring signal', 'portfolio story', 'App UI', 'Design System', 'Public face'];
  check('scientific record copy', required.every((s) => text.includes(s)), required.filter((s) => !text.includes(s)).join(' | '));
  check('anti-slop copy exclusions', forbidden.every((s) => !text.includes(s)), forbidden.filter((s) => text.includes(s)).join(' | '));

  for (const asset of ['site-sample/sample-report.html', 'site-sample/multi/multi-report.html', 'site-sample/confidence_plot.png']) {
    const response = await page.request.get(`${ORIGIN}/${asset}`);
    check(`asset ${asset}`, response.ok(), `status=${response.status()}`);
  }

  await page.getByRole('link', { name: 'Inspect the 17-month example' }).click();
  await page.waitForTimeout(300);
  check('primary CTA reaches evidence', (await page.locator('#evidence').boundingBox()) !== null, page.url());
}

const browser = await chromium.launch({ headless: true });
try {
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const dp = await desktop.newPage();
  const consoleErrors = [];
  dp.on('console', (m) => { if (m.type() === 'error' && !m.text().includes('favicon')) consoleErrors.push(m.text()); });
  dp.on('pageerror', (e) => consoleErrors.push(String(e)));
  await dp.goto(NAV_URL, { waitUntil: 'networkidle', timeout: 60000 });
  await ready(dp);
  await inspect(dp, 'desktop');
  await screenshot(dp, 'desktop-home');
  await dp.locator('#evidence').scrollIntoViewIfNeeded();
  await screenshot(dp, 'desktop-evidence', false);
  await verifyCopyAndAssets(dp);
  check('console clean', consoleErrors.length === 0, consoleErrors.join(' | '));
  await desktop.close();

  const mobile = await browser.newContext({ viewport: { width: 375, height: 812 }, isMobile: true, hasTouch: true });
  const mp = await mobile.newPage();
  await mp.goto(NAV_URL, { waitUntil: 'networkidle', timeout: 60000 });
  await ready(mp);
  await inspect(mp, 'mobile');
  await screenshot(mp, 'mobile-home');
  await mp.locator('#evidence').scrollIntoViewIfNeeded();
  await screenshot(mp, 'mobile-evidence', false);
  await mobile.close();

  result.pass = result.errors.length === 0;
  fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  process.exit(result.pass ? 0 : 1);
} finally {
  await browser.close();
}
