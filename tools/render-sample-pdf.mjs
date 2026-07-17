/** Render a self-contained HTML sample to PDF with Playwright Chromium.
 *
 * Usage: node tools/render-sample-pdf.mjs input.html output.pdf
 */
import { chromium } from 'playwright';
import { pathToFileURL } from 'url';
import path from 'path';

const [inputArg, outputArg] = process.argv.slice(2);
if (!inputArg || !outputArg) {
  throw new Error('Usage: node tools/render-sample-pdf.mjs input.html output.pdf');
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage();
  await page.goto(pathToFileURL(path.resolve(inputArg)).href, {
    waitUntil: 'networkidle',
  });
  await page.pdf({
    path: path.resolve(outputArg),
    format: 'A4',
    printBackground: true,
  });
} finally {
  await browser.close();
}
