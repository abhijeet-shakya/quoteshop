// Re-render design baselines: node apps/quoteshop/docs/qa/render/baselines.mjs
// Copies ../../design/*.dc.html next to support.js (patching broken light tokens), serves the folder with
// python3 http.server, screenshots each file light+dark at its $preview viewport, verifies the render, exits 1 on failure.
import { readdirSync, readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { spawn } from 'node:child_process';
import { createRequire } from 'node:module';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const designDir = resolve(here, '../../design');
const outDir = resolve(here, '../design-baselines');
const pwPath = process.env.PLAYWRIGHT_PATH || resolve(here, '../../../../crm/node_modules/playwright');
const { chromium } = createRequire(import.meta.url)(pwPath);

// CONTRACTS.md §8 canonical light values for tokens that are self-referencing in some design files.
const LIGHT_FIX = '<style>/* qa: canonical light tokens (CONTRACTS §8) */[data-theme="light"]{--panel:#F7F7F4;--field:#F4F4F1;--tile:#F1F1EE;--line:#ECECE8;--border:#E2E2DE;--glass:rgba(255,255,255,0.9)}</style>';

mkdirSync(outDir, { recursive: true });
const files = readdirSync(designDir).filter((f) => f.endsWith('.dc.html')).sort();
const patched = [];
for (const f of files) {
  let src = readFileSync(join(designDir, f), 'utf8');
  if (/\[data-theme="light"\][^}]*--(panel|field|tile|line|border|glass):var\(--\1\)/.test(src)) {
    src = src.replace('</helmet>', LIGHT_FIX + '\n</helmet>');
    patched.push(f);
  }
  writeFileSync(join(here, f), src);
}
console.log('light-token override injected into:', patched.join(', ') || 'none');

const server = spawn('python3', ['-u', '-m', 'http.server', '0', '--bind', '127.0.0.1', '--directory', here]);
const port = await new Promise((ok, fail) => {
  server.stdout.on('data', (d) => { const m = String(d).match(/port (\d+)/); if (m) ok(m[1]); });
  server.on('exit', () => fail(new Error('http.server exited')));
});

// In-page checks: leftovers, theme, loop counts (top-level loops, visible branches only) vs the data.
function verify(expectDark) {
  const root = document.querySelector('x-dc');
  const html = root.innerHTML;
  const res = { leftoverBraces: (html.match(/\{\{/g) || []).length, scTags: root.querySelectorAll('sc-for,sc-if,template[data-sc],helmet').length, loops: [] };
  const themed = root.querySelector('[data-theme]');
  if (themed) {
    res.theme = themed.dataset.theme;
    res.themeOk = res.theme === (expectDark ? 'dark' : 'light');
    res.bg = getComputedStyle(themed).backgroundColor;
    const used = new Set([...(document.head.innerHTML + html).matchAll(/var\((--[\w-]+)\)/g)].map((m) => m[1]));
    res.emptyTokens = [...used].filter((t) => !getComputedStyle(themed).getPropertyValue(t).trim()); // used but unresolved
  }
  const vals = dc.instance.renderVals();
  const get = (e) => e.replace(/[{}\s]/g, '').split('.').reduce((o, k) => o?.[k], vals);
  (function walk(node, visible) {
    for (const el of node.children) {
      if (el.tagName === 'TEMPLATE' && el.dataset.sc === 'if') { walk(el.content, visible && !!get(el.getAttribute('value'))); continue; }
      if (el.tagName === 'TEMPLATE' && el.dataset.sc === 'for') {
        const first = el.content.firstElementChild;
        const style = (first.getAttribute('style') || '').split('{{')[0];
        const expected = visible ? (get(el.getAttribute('list')) || []).length : 0;
        const actual = visible ? [...root.querySelectorAll(first.tagName)].filter((x) => (x.getAttribute('style') || '').startsWith(style)).length : 0;
        res.loops.push({ list: el.getAttribute('list'), hint: +el.getAttribute('hint-placeholder-count'), expected, actual, ok: actual >= expected });
        continue;
      }
      walk(el, visible);
    }
  })(dc.tpl.content, true);
  return res;
}

const browser = await chromium.launch();
let failed = 0;
const summary = [];
try {
  for (const f of files) {
    const name = f.replace('.dc.html', '');
    const preview = JSON.parse(readFileSync(join(here, f), 'utf8').match(/data-props='([^']*)'/)[1]).$preview || {};
    const width = preview.width || (name.startsWith('Mobile') ? 390 : 1280);
    const height = preview.height || 900;
    for (const theme of ['light', 'dark']) {
      const page = await browser.newPage({ viewport: { width, height } });
      const errors = [];
      page.on('pageerror', (e) => errors.push(e.message));
      await page.goto(`http://127.0.0.1:${port}/${f}?dark=${theme === 'dark' ? 1 : 0}`);
      await page.waitForSelector('x-dc[data-ready]', { state: 'attached' });
      await page.evaluate(() => document.fonts.ready);
      const r = await page.evaluate(verify, theme === 'dark');
      await page.screenshot({ path: join(outDir, `${name}-${theme}.png`), fullPage: true });
      if (width < 600) { // phone frames scroll internally: also capture the whole scroll content
        const grew = await page.evaluate(() => {
          const frame = document.querySelector('x-dc > div');
          frame.style.height = 'auto'; frame.style.minHeight = frame.offsetHeight + 'px';
          for (const el of frame.querySelectorAll('*')) if (/auto|scroll/.test(getComputedStyle(el).overflowY)) { el.style.overflowY = 'visible'; el.style.flex = 'none'; }
          return document.documentElement.scrollHeight > innerHeight;
        });
        if (grew) await page.screenshot({ path: join(outDir, `${name}-${theme}-unrolled.png`), fullPage: true });
      }
      const ok = !errors.length && !r.leftoverBraces && !r.scTags && r.themeOk !== false && !(r.emptyTokens || []).length && r.loops.every((l) => l.ok);
      if (!ok) failed++;
      summary.push({ file: name, theme, viewport: `${width}x${height}`, ok, bg: r.bg, loops: r.loops.map((l) => `${l.list}=${l.actual}/${l.expected}`).join(' '), errors: errors.join('; '), emptyTokens: (r.emptyTokens || []).join(' ') });
      await page.close();
    }
  }
  // Interaction smoke: theme toggle + setState re-render on Main.
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  await page.goto(`http://127.0.0.1:${port}/Main.dc.html?dark=0`);
  await page.waitForSelector('x-dc[data-ready]', { state: 'attached' });
  await page.click('button[aria-label="Switch to dark mode"]');
  const toggled = await page.getAttribute('x-dc [data-theme]', 'data-theme');
  console.log('Main toggleTheme click -> data-theme =', toggled);
  if (toggled !== 'dark') failed++;
} finally {
  await browser.close();
  server.kill();
}
console.table(summary);
console.log(failed ? `FAILED: ${failed}` : 'all checks passed');
process.exit(failed ? 1 : 0);
