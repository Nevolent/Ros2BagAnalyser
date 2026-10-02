import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { apiFixture, job } from './api-fixture';
import type { Overview } from '../src/data/api-types';

test('one recording keeps its card, elapsed time and estimate across outputs and handoffs', async ({
  page,
}) => {
  const api = await apiFixture(page);
  let progress: Overview['recording_progress'] = {
    run_id: 9,
    recording_id: 42,
    recording_name: 'recording-42',
    active_job_id: 9,
    elapsed_ms: 20000,
    estimated_total_ms: 100000,
    estimate_status: 'available',
    waiting: false,
  };
  api.active!.active_elapsed_ms = 20000;
  api.queue = [
    { ...job(10, 'topdown_preview'), recording_id: 42 },
    { ...job(11, 'imu_series'), recording_id: 42 },
  ];
  api.override = async (route, path) => {
    if (path !== '/api/v1/processing/overview') return false;
    await route.fulfill({
      json: {
        current: api.active,
        queue: api.queue,
        recording_progress: progress,
        worker_online: true,
        recommended_poll_interval_ms: 1000,
      },
    });
    return true;
  };
  await page.goto('/#/processing');
  const card = page.getByRole('region', { name: 'Active processing job' });
  await expect(card).toBeVisible();
  await card.evaluate((el) => el.setAttribute('data-original-card', 'true'));
  const bar = page.getByRole('progressbar');
  await expect(bar).toHaveAttribute('aria-valuenow', '20');
  api.active = null;
  progress = { ...progress, active_job_id: 10, elapsed_ms: 40000, waiting: true };
  await expect(bar).toHaveAttribute('aria-valuenow', '40');
  await expect(card).toHaveAttribute('data-original-card', 'true');
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(0);
  api.active = { ...api.queue.shift()!, state: 'running', active_elapsed_ms: 1000 };
  progress = { ...progress, elapsed_ms: 41000, waiting: false };
  await expect(bar).toHaveAttribute('aria-valuenow', '41');
  api.active = { ...api.queue.shift()!, state: 'running', active_elapsed_ms: 1000 };
  progress = { ...progress, active_job_id: 11, elapsed_ms: 81000 };
  await expect(bar).toHaveAttribute('aria-valuenow', '81');
  await expect(card).toHaveAttribute('data-original-card', 'true');
  await expect(card).toContainText('1:40');
  api.active = null;
  progress = null;
  await expect(card).toHaveCount(0);
});

test('optional ready outputs cannot mark missing or empty front input ready', async ({ page }) => {
  const api = await apiFixture(page);
  api.recording.outputs[0] = {
    kind: 'front_preview',
    state: 'unavailable',
    diagnostic: {
      code: 'front_topic_empty',
      message: 'The configured front camera topic is empty.',
    },
  };
  await page.goto('/');
  const row = page
    .locator('tbody tr')
    .filter({ has: page.getByRole('link', { name: 'recording-42', exact: true }) });
  await expect(row).toContainText('Failed');
  await row.getByRole('link').click();
  await expect(page.locator('.recording-errors')).toContainText('front_topic_empty');
});

test('fresh camera requests recover automatically and persistent failures offer retry', async ({
  page,
}) => {
  const api = await apiFixture(page);
  const source = readFileSync('../tools/serve_frontend_mock.py', 'utf8');
  const media = Buffer.from(
    source.match(/MOCK_VIDEO = base64.b64decode\(\s*"([A-Za-z0-9+/=]+)"/)![1],
    'base64',
  );
  const attempts = new Map<string, number>();
  let topReady = false;
  api.override = async (route, path) => {
    if (!path.includes('/media/')) return false;
    const count = (attempts.get(path) ?? 0) + 1;
    attempts.set(path, count);
    if (count === 1 || (path.includes('topdown') && !topReady)) {
      await route.fulfill({ status: 503, body: '' });
      return true;
    }
    const range = route
      .request()
      .headers()
      .range?.match(/^bytes=(\d+)-(\d*)$/);
    const start = range ? Number(range[1]) : 0;
    const end = range?.[2] ? Number(range[2]) : media.length - 1;
    await route.fulfill({
      status: range ? 206 : 200,
      contentType: 'video/mp4',
      headers: {
        'Accept-Ranges': 'bytes',
        ...(range ? { 'Content-Range': `bytes ${start}-${end}/${media.length}` } : {}),
      },
      body: media.subarray(start, end + 1),
    });
    return true;
  };
  await page.goto('/#/analysis/42');
  await expect(page.locator('.analysis-camera-front [data-camera-state]')).toHaveText(
    'Loading camera…',
  );
  await expect(page.locator('.recording-errors')).toHaveCount(0);
  const front = page.locator('.analysis-camera-front video');
  await expect
    .poll(() => front.evaluate((el: HTMLVideoElement) => el.readyState))
    .toBeGreaterThanOrEqual(2);
  await page.getByRole('slider').press('ArrowRight');
  await expect(front).toHaveCSS('visibility', 'visible');
  await expect(page.locator('.recording-errors')).not.toContainText(
    'Front camera could not be loaded.',
  );
  const retry = page.getByRole('button', { name: 'Retry top camera' });
  await expect(retry).toBeVisible({ timeout: 10000 });
  const requestsAtFailure = attempts.get('/api/recordings/42/topdown-preview/media/2');
  await page.waitForTimeout(1200);
  expect(attempts.get('/api/recordings/42/topdown-preview/media/2')).toBe(requestsAtFailure);
  topReady = true;
  await retry.click();
  await expect
    .poll(() =>
      page.locator('.analysis-camera-top video').evaluate((el: HTMLVideoElement) => el.readyState),
    )
    .toBeGreaterThanOrEqual(2);
  await expect(page.locator('.recording-errors')).toHaveCount(0);
  await expect(retry).toHaveCount(0);
});

test('timeline cursor remains a continuous line during playback and scrubbing', async ({
  page,
}) => {
  const { PNG } = await import('pngjs');
  await page.clock.install({ time: new Date('2026-09-28T10:00:00Z') });
  await page.clock.pauseAt(new Date('2026-09-28T10:00:00Z'));
  await page.goto('/?demo=1#/analysis');
  await page.clock.runFor(100);
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  const box = (await plot.boundingBox())!;
  for (const fraction of [0.2, 0.5, 0.9]) {
    await page.mouse.click(box.x + box.width * fraction, box.y + 60);
    await page.getByRole('button', { name: 'Play timeline', exact: true }).click();
    await page.clock.runFor(1000);
    const cursor = (await page.locator('.timeline-cursor').boundingBox())!;
    const readout = (await page.locator('.timeline-measurement').boundingBox())!;
    expect(cursor.y - (readout.y + readout.height)).toBeGreaterThanOrEqual(1);
    expect(cursor.y - (readout.y + readout.height)).toBeLessThanOrEqual(3);
    const capture = PNG.sync.read(await page.screenshot());
    for (let y = Math.ceil(cursor.y) + 1; y < cursor.y + cursor.height - 1; y++) {
      const x = Math.floor(cursor.x);
      const luminance = [x - 1, x, x + 1].map(
        (column) => capture.data[(y * capture.width + column) * 4],
      );
      expect(Math.max(...luminance), `cursor must stay painted at y=${y}`).toBeGreaterThan(100);
    }
    await page.getByRole('button', { name: 'Pause timeline', exact: true }).click();
  }
});
