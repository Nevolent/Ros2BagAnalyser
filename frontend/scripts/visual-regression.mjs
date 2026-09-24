import { chromium } from '@playwright/test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { PNG } from 'pngjs';
import pixelmatch from 'pixelmatch';

const mode = process.argv[2] ?? 'compare';
const root = process.env.VISUAL_OUTPUT_DIR || 'artifacts/react-migration';
if (!['baseline', 'compare'].includes(mode)) throw new Error('Use baseline or compare.');
if (mode === 'compare' && !existsSync(`${root}/baseline`))
  throw new Error(
    'No visual baseline found. Run npm run visual:capture against the approved UI first.',
  );
const destination = `${root}/${mode === 'baseline' ? 'baseline' : 'current'}`;
mkdirSync(destination, { recursive: true });
const cached = join(
  homedir(),
  'Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell',
);
const browser = await chromium.launch({
  executablePath: process.env.CHROMIUM_PATH || (existsSync(cached) ? cached : undefined),
});
const results = [];
try {
  for (const width of [390, 768, 1440, 1920]) {
    for (const theme of ['dark', 'light']) {
      for (const route of ['recordings', 'processing', 'analysis']) {
        if (
          process.env.VISUAL_CASE &&
          !`${route}-${width}-${theme}`.includes(process.env.VISUAL_CASE)
        )
          continue;
        const page = await browser.newPage({
          viewport: { width, height: 1000 },
          colorScheme: theme,
          timezoneId: 'Europe/Tallinn',
          reducedMotion: 'reduce',
        });
        await page.clock.install({ time: new Date('2026-09-21T09:00:00Z') });
        await page.clock.pauseAt(new Date('2026-09-21T09:00:00Z'));
        await page.goto(`${process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173'}/#/${route}`);
        await page.locator('.dashboard-workspace').waitFor();
        await page.evaluate(async (theme) => {
          document.documentElement.classList.toggle('dark', theme === 'dark');
          document.documentElement.style.colorScheme = theme;
          await document.fonts.ready;
        }, theme);
        // Flush layout/ResizeObservers without advancing the simulated job clock.
        await page.clock.runFor(100);
        async function capture(suffix = '') {
          const name = `${route}-${width}-${theme}${suffix}.png`;
          const buffer = await page.screenshot({
            path: `${destination}/${name}`,
            animations: 'disabled',
          });
          if (mode === 'baseline') return;
          const before = PNG.sync.read(readFileSync(`${root}/baseline/${name}`));
          const after = PNG.sync.read(buffer);
          const diff = new PNG({ width: after.width, height: after.height });
          const pixels = pixelmatch(before.data, after.data, diff.data, after.width, after.height, {
            threshold: 0.1,
          });
          results.push({
            name,
            pixels,
            percent: +((pixels / (after.width * after.height)) * 100).toFixed(4),
          });
          if (pixels)
            writeFileSync(
              `${destination}/${name.replace('.png', '-diff.png')}`,
              PNG.sync.write(diff),
            );
        }
        await capture();
        if (width === 1440 && theme === 'dark') {
          if (route === 'recordings') {
            await page.getByRole('checkbox', { name: 'Select all visible bags' }).check();
            await page.getByRole('button', { name: 'Prepare Selected' }).click();
            await capture('-prepare');
            await page.keyboard.press('Escape');
            await page.getByRole('button', { name: 'Filter by analysis' }).click();
            await capture('-filter');
            await page.keyboard.press('Escape');
            await page.keyboard.press('Control+k');
            await capture('-search');
          } else if (route === 'processing') {
            await page.getByRole('button', { name: 'Failures', exact: true }).click();
            await capture('-failures');
            await page.locator('[data-failure-details]').nth(1).click();
            await capture('-failure-dialog');
          } else {
            await page.locator('[data-channel-trigger]').click();
            await capture('-channels');
          }
        }
        await page.close();
      }
    }
  }
} finally {
  await browser.close();
}
if (mode !== 'baseline') {
  writeFileSync(`${root}/comparison.json`, JSON.stringify(results, null, 2) + '\n');
  console.table(results);
  if (results.some((result) => result.pixels > 0)) process.exitCode = 1;
} else console.log('Captured 30 tailored UI baselines.');
