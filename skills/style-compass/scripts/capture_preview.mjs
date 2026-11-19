#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const require = createRequire(import.meta.url);

function loadPlaywright() {
  if (process.env.PLAYWRIGHT_MODULE) {
    const p = require(process.env.PLAYWRIGHT_MODULE);
    const exe = p?.chromium?.executablePath?.();
    if (exe && fs.existsSync(exe)) return p;
  }
  try {
    const p = require('playwright');
    const exe = p?.chromium?.executablePath?.();
    if (exe && fs.existsSync(exe)) return p;
  } catch {}
  const home = process.env.HOME || '';
  const cache = path.join(home, '.npm', '_npx');
  if (home && fs.existsSync(cache)) {
    for (const dir of fs.readdirSync(cache).sort()) {
      const mod = path.join(cache, dir, 'node_modules', 'playwright');
      if (fs.existsSync(path.join(mod, 'package.json'))) {
        try {
          const p = require(mod);
          const exe = p?.chromium?.executablePath?.();
          if (exe && fs.existsSync(exe)) return p;
        } catch {}
      }
    }
  }
  return null;
}

function parseViewport(raw, fallback) {
  const m = String(raw || '').match(/^(\d+)x(\d+)$/i);
  if (!m) return fallback;
  return { width: Number(m[1]), height: Number(m[2]) };
}

function parseArgs(argv) {
  const args = {
    html: '',
    out: '',
    name: '',
    desktop: { width: 1440, height: 900 },
    mobile: { width: 390, height: 844 },
    click: '',
    wait: 550,
    noMobile: false,
    fullPage: false,
  };
  for (let i = 0; i < argv.length; i += 1) {
    const flag = argv[i];
    if (flag === '--html') args.html = argv[++i] || '';
    else if (flag === '--out') args.out = argv[++i] || '';
    else if (flag === '--name') args.name = argv[++i] || '';
    else if (flag === '--desktop') args.desktop = parseViewport(argv[++i], args.desktop);
    else if (flag === '--mobile') args.mobile = parseViewport(argv[++i], args.mobile);
    else if (flag === '--click') args.click = argv[++i] || '';
    else if (flag === '--wait') args.wait = Math.max(0, Number(argv[++i] || 550));
    else if (flag === '--no-mobile') args.noMobile = true;
    else if (flag === '--full-page') args.fullPage = true;
    else {
      return { error: `Unknown argument: ${flag}` };
    }
  }
  if (!args.html || !args.out) {
    return { error: 'Usage: capture_preview.mjs --html <file> --out <dir> [--name preview] [--desktop 1440x900] [--mobile 390x844] [--click "<selector>"] [--wait 550] [--no-mobile] [--full-page]' };
  }
  if (!args.name) {
    args.name = path.basename(args.html, path.extname(args.html)) || 'preview';
  }
  return { args };
}

const parsed = parseArgs(process.argv.slice(2));
if (parsed.error) {
  console.log(JSON.stringify({ ok: false, browserAvailable: false, error: parsed.error }, null, 2));
  process.exit(2);
}

const { args } = parsed;
const htmlPath = path.resolve(args.html);
if (!fs.existsSync(htmlPath)) {
  console.log(JSON.stringify({ ok: false, browserAvailable: false, error: `HTML file not found: ${htmlPath}` }, null, 2));
  process.exit(2);
}

const pw = loadPlaywright();
if (!pw) {
  console.log(JSON.stringify({
    ok: false,
    browserAvailable: false,
    error: 'Playwright + Chromium cache not found; set PLAYWRIGHT_MODULE or use host browser tool.',
  }, null, 2));
  process.exit(1);
}

const outDir = path.resolve(args.out);
fs.mkdirSync(outDir, { recursive: true });
const targetUrl = pathToFileURL(htmlPath).href;
const consoleErrors = [];
const pageErrors = [];
const screenshots = {};

const executablePath = pw.chromium.executablePath();
let browser;
try {
  browser = await pw.chromium.launch({ headless: true, executablePath });

  const ctx = await browser.newContext({
    viewport: args.desktop,
    deviceScaleFactor: 2,
    locale: 'zh-CN',
  });
  const page = await ctx.newPage();
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });
  page.on('pageerror', (err) => {
    pageErrors.push(err?.message || String(err));
  });

  await page.goto(targetUrl, { waitUntil: 'load' });
  await page.waitForTimeout(args.wait);

  const desktopMetrics = await page.evaluate(() => ({
    scrollWidth: document.documentElement.scrollWidth,
    innerWidth: window.innerWidth,
    scrollHeight: document.documentElement.scrollHeight,
    overflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
  }));

  const desktopShot = path.join(outDir, `${args.name}-desktop.png`);
  await page.screenshot({ path: desktopShot, fullPage: args.fullPage });
  screenshots.desktop = desktopShot;

  let clickOk = null;
  if (args.click) {
    const loc = page.locator(args.click).first();
    await loc.waitFor({ state: 'visible', timeout: 3000 });
    await loc.click();
    await page.waitForTimeout(400);
    const stateShot = path.join(outDir, `${args.name}-state.png`);
    await page.screenshot({ path: stateShot, fullPage: args.fullPage });
    screenshots.state = stateShot;
    clickOk = true;
  }
  await ctx.close();

  let mobileMetrics = null;
  if (!args.noMobile) {
    const mCtx = await browser.newContext({
      viewport: args.mobile,
      deviceScaleFactor: 2,
      locale: 'zh-CN',
      hasTouch: true,
    });
    const mPage = await mCtx.newPage();
    mPage.on('console', (msg) => {
      if (msg.type() === 'error') consoleErrors.push(`[mobile] ${msg.text()}`);
    });
    mPage.on('pageerror', (err) => {
      pageErrors.push(`[mobile] ${err?.message || String(err)}`);
    });
    await mPage.goto(targetUrl, { waitUntil: 'load' });
    await mPage.waitForTimeout(args.wait);
    mobileMetrics = await mPage.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      innerWidth: window.innerWidth,
      scrollHeight: document.documentElement.scrollHeight,
      overflowX: document.documentElement.scrollWidth > window.innerWidth + 1,
    }));
    const mobileShot = path.join(outDir, `${args.name}-mobile.png`);
    await mPage.screenshot({ path: mobileShot, fullPage: args.fullPage });
    screenshots.mobile = mobileShot;
    await mCtx.close();
  }

  const ok = !desktopMetrics.overflowX
    && !(mobileMetrics && mobileMetrics.overflowX)
    && consoleErrors.length === 0
    && pageErrors.length === 0;

  console.log(JSON.stringify({
    ok,
    browserAvailable: true,
    executablePath,
    html: htmlPath,
    desktopOverflowX: desktopMetrics.overflowX,
    desktopMetrics,
    mobileOverflowX: mobileMetrics ? mobileMetrics.overflowX : null,
    mobileMetrics,
    clickApplied: clickOk,
    consoleErrors,
    pageErrors,
    screenshots,
  }, null, 2));
  process.exit(ok ? 0 : 1);
} catch (err) {
  console.log(JSON.stringify({
    ok: false,
    browserAvailable: true,
    error: err?.message || String(err),
    consoleErrors,
    pageErrors,
    screenshots,
  }, null, 2));
  process.exit(1);
} finally {
  if (browser) await browser.close();
}
