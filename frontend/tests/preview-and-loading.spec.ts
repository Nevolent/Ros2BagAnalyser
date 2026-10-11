import { expect, test } from '@playwright/test';
import { PNG } from 'pngjs';
import { apiFixture } from './api-fixture';

test('five frames share one request, start at the middle, cycle on hover and honor reduced motion', async ({
  page,
}) => {
  await page.clock.install();
  const api = await apiFixture(page);
  api.recording.thumbnail_url = '/api/recordings/42/thumbnail/media/8';
  api.recording.thumbnail_frame_count = 5;
  api.recording.outputs.push({ kind: 'thumbnail', state: 'ready', diagnostic: null });
  api.catalog.recordings = [api.recording];
  const strip = new PNG({ width: 160, height: 18 });
  for (let i = 0; i < strip.data.length; i += 4) {
    strip.data[i] = Math.floor(((i / 4) % 160) / 32) * 50;
    strip.data[i + 3] = 255;
  }
  const png = PNG.sync.write(strip);
  let downloads = 0;
  api.override = async (route, path) => {
    if (path !== api.recording.thumbnail_url) return false;
    downloads++;
    await route.fulfill({ contentType: 'image/png', body: png });
    return true;
  };
  await page.goto('/');
  const preview = page.locator('.recording-thumbnail');
  await expect(preview.locator('img')).toBeVisible();
  await expect(preview.locator('.thumbnail-loading')).toHaveCount(0);
  await expect(preview).toHaveAttribute('data-thumbnail-frame', '2');
  await preview.hover();
  await page.clock.runFor(650);
  await expect(preview).toHaveAttribute('data-thumbnail-frame', '3');
  await page.clock.runFor(650);
  await expect(preview).toHaveAttribute('data-thumbnail-frame', '4');
  expect(downloads).toBe(1);
  await page.mouse.move(0, 0);
  await expect(preview).toHaveAttribute('data-thumbnail-frame', '2');
  const link = page.getByRole('link', { name: `Analyze ${api.recording.name}` });
  await link.focus();
  await page.clock.runFor(650);
  await expect(preview).toHaveAttribute('data-thumbnail-frame', '3');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(preview).toHaveAttribute('data-thumbnail-frame', '2');
  await link.blur();
  await preview.hover();
  await page.clock.runFor(2600);
  await expect(preview).toHaveAttribute('data-thumbnail-frame', '2');
  expect(downloads).toBe(1);
});

test('prepared cameras appear before a delayed sensor download completes', async ({ page }) => {
  const api = await apiFixture(page);
  let release!: () => void;
  const gate = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.override = async (route, path) => {
    if (path !== '/api/recordings/42/imu-series/data/3') return false;
    await gate;
    await route.fulfill({ json: api.imu.data });
    return true;
  };
  await page.goto('/#/analysis/42');
  try {
    await expect(page.locator('.analysis-recording-name')).toHaveText('recording-42');
    await expect(page.locator('.analysis-camera-front video')).toHaveAttribute(
      'src',
      api.recording.outputs[0].artifact!.url,
    );
    await expect(page.getByText('Loading recording…', { exact: true })).toHaveCount(0);
    await expect(page.getByText('Loading sensor data…', { exact: true })).toBeVisible();
  } finally {
    release();
  }
  await expect(page.getByRole('checkbox', { name: 'Z axis' })).toBeEnabled();
  await expect(page.getByText('Loading sensor data…', { exact: true })).toHaveCount(0);
});
