/**
 * One-shot QA for the OpenPharmaStability public website preview.
 *
 * Deploy folder (default) — serve site/ first:
 *   python -m http.server 8766 --directory site
 *   npx -y -p playwright node tools/website-qa.mjs
 *
 * Authoring source (--dev) — serve repo root first:
 *   python -m http.server 8766
 *   npx -y -p playwright node tools/website-qa.mjs --dev
 *
 * Production (--base) — no local server required:
 *   npx -y -p playwright node tools/website-qa.mjs --base https://openpharmastability.pages.dev
 */
import { chromium } from 'playwright';
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const OUT = path.join(ROOT, 'qa-output');
const DEV = process.argv.includes('--dev');
const baseArgIdx = process.argv.indexOf('--base');
const REMOTE_BASE = baseArgIdx !== -1 ? process.argv[baseArgIdx + 1]?.replace(/\/$/, '') : null;
const LOCAL_ORIGIN = 'http://127.0.0.1:8766';
const ORIGIN = REMOTE_BASE || LOCAL_ORIGIN;
const BASE = REMOTE_BASE
  ? `${REMOTE_BASE}/`
  : DEV
    ? `${LOCAL_ORIGIN}/OpenPharmaStability.dc.html`
    : `${LOCAL_ORIGIN}/`;

fs.mkdirSync(OUT, { recursive: true });

const results = { screenshots: [], interactions: [], regressions: [], errors: [] };

async function waitBoot(page) {
  await page.waitForFunction(() => window.__dcBoot && document.querySelector('#dc-root'), { timeout: 30000 });
  await page.waitForTimeout(800);
  await page.waitForFunction(
    () => !document.querySelector('.sc-logic-error') && document.body.innerText.includes('OpenPharmaStability'),
    { timeout: 30000 }
  );
}

async function shot(page, name) {
  const file = path.join(OUT, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  results.screenshots.push(file);
  return file;
}

async function checkLayout(page, label) {
  const issues = await page.evaluate(() => {
    const out = [];
    const logicErr = document.querySelector('.sc-logic-error');
    if (logicErr) out.push(`logic_error:${logicErr.textContent?.slice(0, 120)}`);
    const home = document.getElementById('view-home');
    if (home && getComputedStyle(home).display !== 'none') {
      const nav = document.querySelector('.ops-nav');
      const h1 = document.querySelector('.ops-h1');
      if (nav && h1) {
        const nr = nav.getBoundingClientRect();
        const hr = h1.getBoundingClientRect();
        if (hr.top < nr.bottom - 2) out.push('hero_h1_overlaps_nav');
      }
      const heroGrid = document.querySelector('.ops-2');
      if (heroGrid) {
        const kids = [...heroGrid.children];
        if (kids.length >= 2) {
          const a = kids[0].getBoundingClientRect();
          const b = kids[1].getBoundingClientRect();
          if (a.bottom > b.top + 40 && a.right > b.left + 20 && b.right > a.left + 20) {
            out.push('hero_columns_overlap');
          }
        }
      }
    }
    return out;
  });
  if (issues.length) results.regressions.push({ label, issues });
  return issues;
}

async function clickNav(page, text) {
  await page.getByRole('button', { name: text, exact: true }).click();
  await page.waitForTimeout(400);
}

async function runInteractions(page) {
  const log = (name, ok, detail = '') => {
    results.interactions.push({ name, ok, detail });
    if (!ok) results.errors.push(`${name}: ${detail}`);
  };

  // Overview -> App UI
  await clickNav(page, 'Overview');
  const homeVisible = await page.evaluate(() => getComputedStyle(document.getElementById('view-home')).display !== 'none');
  log('Overview visible on load', homeVisible);

  await clickNav(page, 'App UI');
  const appVisible = await page.evaluate(() => getComputedStyle(document.getElementById('view-app')).display !== 'none');
  log('Overview -> App UI', appVisible, appVisible ? '' : 'view-app not visible');

  // App UI -> Warnings 2
  await page.getByRole('button', { name: 'Warnings 2', exact: true }).click();
  await page.waitForTimeout(300);
  const warnVisible = await page.evaluate(() => {
    const el = [...document.querySelectorAll('div')].find((d) => d.textContent?.includes('Slope poolability rejected'));
    if (!el) return false;
    let n = el;
    while (n && n !== document.body) {
      if (getComputedStyle(n).display === 'none') return false;
      n = n.parentElement;
    }
    return true;
  });
  log('App UI -> Warnings 2', warnVisible);

  // App UI -> JSON record
  await page.getByRole('button', { name: 'JSON record', exact: true }).click();
  await page.waitForTimeout(300);
  const jsonVisible = await page.evaluate(() => {
    const pres = [...document.querySelectorAll('#view-app pre')].filter((pre) => pre.offsetParent !== null);
    return pres.some((pre) => pre.textContent?.includes('supported_shelf_life_months'));
  });
  log('App UI -> JSON record', jsonVisible);

  // Design System tab
  await clickNav(page, 'Design System');
  const designVisible = await page.evaluate(() => getComputedStyle(document.getElementById('view-design')).display !== 'none');
  log('Design System tab', designVisible);

  // Sample report links -> site-sample/
  await clickNav(page, 'Overview');
  await page.evaluate(() => {
    const el = document.getElementById('report');
    if (el) el.scrollIntoView({ block: 'start' });
  });
  await page.waitForTimeout(500);

  const linkChecks = [
    { label: 'HTML report', href: 'site-sample/sample-report.html', expect: 'Stability' },
    { label: 'JSON record', href: 'site-sample/sample-report.json', expect: 'supported_shelf_life_months' },
    { label: 'confidence plot', href: 'site-sample/confidence_plot.png', expect: null },
  ];

  for (const lc of linkChecks) {
    const href = await page.locator(`a[href="${lc.href}"]`).first().getAttribute('href');
    const hrefOk = href === lc.href && !href.includes('build/');
    if (!hrefOk) {
      log(`Sample link ${lc.label}`, false, `href=${href}`);
      continue;
    }
    const assetUrl = REMOTE_BASE ? `${REMOTE_BASE}/${lc.href}` : `${ORIGIN}/${lc.href}`;
    const resp = await page.request.get(assetUrl);
    const statusOk = resp.ok();
    let contentOk = statusOk;
    if (statusOk && lc.expect && !lc.href.endsWith('.png')) {
      const body = await resp.text();
      contentOk = body.includes(lc.expect);
    } else if (statusOk && lc.href.endsWith('.png')) {
      contentOk = (resp.headers()['content-type'] || '').includes('image');
    }
    log(`Sample link ${lc.label}`, hrefOk && contentOk, `status=${resp.status()} path=${lc.href}`);
  }
}

const browser = await chromium.launch({ headless: true });
try {
  // Desktop
  const desktop = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const dPage = await desktop.newPage();
  const consoleErrors = [];
  dPage.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  dPage.on('pageerror', (err) => consoleErrors.push(String(err)));

  await dPage.goto(BASE, { waitUntil: 'networkidle', timeout: 60000 });
  await waitBoot(dPage);
  await checkLayout(dPage, 'desktop-home');
  await shot(dPage, 'desktop-home');

  await clickNav(dPage, 'App UI');
  await checkLayout(dPage, 'desktop-app');
  await shot(dPage, 'desktop-app');

  await clickNav(dPage, 'Design System');
  await checkLayout(dPage, 'desktop-design');
  await shot(dPage, 'desktop-design');

  await clickNav(dPage, 'Overview');
  await dPage.evaluate(() => document.getElementById('report')?.scrollIntoView());
  await dPage.waitForTimeout(400);
  await shot(dPage, 'desktop-sample-report');

  await runInteractions(dPage);

  if (consoleErrors.length) {
    const critical = consoleErrors.filter((e) => !e.includes('favicon'));
    if (critical.length) results.regressions.push({ label: 'console', issues: critical.slice(0, 5) });
  }

  await desktop.close();

  // Mobile
  const mobile = await browser.newContext({
    viewport: { width: 375, height: 812 },
    isMobile: true,
    hasTouch: true,
  });
  const mPage = await mobile.newPage();
  await mPage.goto(BASE, { waitUntil: 'networkidle', timeout: 60000 });
  await waitBoot(mPage);
  await checkLayout(mPage, 'mobile-home');
  await shot(mPage, 'mobile-home');

  await clickNav(mPage, 'App UI');
  await checkLayout(mPage, 'mobile-app');
  await shot(mPage, 'mobile-app');

  await clickNav(mPage, 'Design System');
  await checkLayout(mPage, 'mobile-design');
  await shot(mPage, 'mobile-design');

  await mobile.close();

  results.pass = results.regressions.length === 0 && results.errors.length === 0;
  fs.writeFileSync(path.join(OUT, 'results.json'), JSON.stringify(results, null, 2));
  console.log(JSON.stringify(results, null, 2));
  process.exit(results.pass ? 0 : 1);
} finally {
  await browser.close();
}
