/**
 * Build the static deploy folder at site/ from authoring sources.
 * Run: node tools/sync-site.mjs
 */
import fs from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(__dirname, '..');
const SITE = path.join(ROOT, 'site');

const LINK_FIXES = [
  ['href="README.md"', 'href="https://github.com/priyamthakar/OpenPharmaStability/blob/main/README.md"'],
  ['href="OpenPharmaStability.md"', 'href="https://github.com/priyamthakar/OpenPharmaStability/blob/main/OpenPharmaStability.md"'],
  ['href="CHANGELOG.md"', 'href="https://github.com/priyamthakar/OpenPharmaStability/blob/main/CHANGELOG.md"'],
];

function applyLinkFixes(html) {
  let out = html;
  for (const [from, to] of LINK_FIXES) {
    out = out.replaceAll(from, to);
  }
  return out;
}

function copyFile(src, dest) {
  fs.mkdirSync(path.dirname(dest), { recursive: true });
  fs.copyFileSync(src, dest);
}

function copyDir(srcDir, destDir) {
  fs.mkdirSync(destDir, { recursive: true });
  for (const entry of fs.readdirSync(srcDir, { withFileTypes: true })) {
    const src = path.join(srcDir, entry.name);
    const dest = path.join(destDir, entry.name);
    if (entry.isDirectory()) copyDir(src, dest);
    else copyFile(src, dest);
  }
}

const written = [];

const dcSrc = path.join(ROOT, 'OpenPharmaStability.dc.html');
const indexDest = path.join(SITE, 'index.html');
const html = applyLinkFixes(fs.readFileSync(dcSrc, 'utf8'));
fs.mkdirSync(SITE, { recursive: true });
fs.writeFileSync(indexDest, html);
written.push('site/index.html');

copyFile(path.join(ROOT, 'support.js'), path.join(SITE, 'support.js'));
written.push('site/support.js');

copyDir(path.join(ROOT, 'site-sample'), path.join(SITE, 'site-sample'));
for (const name of fs.readdirSync(path.join(SITE, 'site-sample'))) {
  written.push(`site/site-sample/${name}`);
}

console.log('Synced deploy folder:');
for (const f of written) console.log(`  ${f}`);
