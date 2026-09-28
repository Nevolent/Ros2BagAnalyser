import { test, expect, type Page } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { apiFixture } from './api-fixture';

async function mediaFixture(page: Page) {
  const api = await apiFixture(page);
  const source = readFileSync('../tools/serve_frontend_mock.py', 'utf8');
  const media = Buffer.from(
    source.match(/MOCK_VIDEO = base64.b64decode\(\s*"([A-Za-z0-9+/=]+)"/)![1],
    'base64',
  );
  // The synthetic H.264 clip is one second long.
  for (const output of api.recording.outputs.slice(0, 2)) {
    output.artifact!.coverage_start_ns = '0';
    output.artifact!.coverage_end_ns = '1000000000';
  }
  let requests = 0;
  api.override = async (route, path) => {
    if (!path.includes('/media/')) return false;
    requests++;
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
  const videos = page.locator('.analysis-camera video');
  await expect(videos).toHaveCount(2);
  for (const video of await videos.all())
    await expect
      .poll(() => video.evaluate((el: HTMLVideoElement) => el.readyState))
      .toBeGreaterThanOrEqual(2);
  return { videos, requests: () => requests };
}

test('both H.264 cameras keep decoding after repeated backward and forward scrubs', async ({
  page,
}) => {
  const errors: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  const media = await mediaFixture(page);
  const initialRequests = media.requests();
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  // Zoom to make the short synthetic camera coverage usable for pointer scrubbing.
  for (let i = 0; i < 3; i++)
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  const box = (await plot.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.1, box.y + 50);
  await page.mouse.down();
  for (let i = 0; i < 12; i++)
    await page.mouse.move(box.x + box.width * (i % 2 ? 0.1 : 0.9), box.y + 50, { steps: 8 });
  await page.mouse.move(box.x + box.width * 0.2, box.y + 50);
  await page.mouse.up();
  const time = Number(await plot.getAttribute('aria-valuenow'));
  for (const video of await media.videos.all()) {
    await expect.poll(() => video.evaluate((el: HTMLVideoElement) => el.seeking)).toBe(false);
    expect(await video.evaluate((el: HTMLVideoElement) => el.currentTime)).toBeCloseTo(time, 2);
    await expect(video).toHaveCSS('visibility', 'visible');
  }
  await media.videos.evaluateAll((videos) => {
    for (const video of videos as HTMLVideoElement[]) {
      let frames = 0;
      const decoded = () => {
        video.dataset.frames = String(++frames);
        video.requestVideoFrameCallback(decoded);
      };
      video.requestVideoFrameCallback(decoded);
    }
  });
  await page.getByRole('button', { name: 'Play timeline', exact: true }).click();
  await expect
    .poll(() =>
      media.videos.evaluateAll((videos) =>
        videos.every((video) => Number((video as HTMLElement).dataset.frames) >= 3),
      ),
    )
    .toBe(true);
  await page.getByRole('button', { name: 'Pause timeline', exact: true }).click();
  expect(media.requests()).toBe(initialRequests);
  expect(errors).toEqual([]);
  await expect(page.getByRole('button', { name: /Retry .* camera/ })).toHaveCount(0);
});

test('a decoder stalled without a media error reloads and restores the paused frame', async ({
  page,
}) => {
  await page.clock.install({ time: new Date('2026-09-28T12:00:00Z') });
  await page.clock.pauseAt(new Date('2026-09-28T12:00:00Z'));
  const media = await mediaFixture(page);
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  const box = (await plot.boundingBox())!;
  await plot.click({ position: { x: box.width / 12, y: 50 } });
  const front = media.videos.first();
  await expect.poll(() => front.evaluate((video: HTMLVideoElement) => video.seeking)).toBe(false);
  const time = Number(await plot.getAttribute('aria-valuenow'));
  await front.evaluate((video: HTMLVideoElement) => {
    const load = video.load.bind(video);
    Object.defineProperty(video, 'seeking', { configurable: true, value: true });
    Object.defineProperty(video, 'readyState', { configurable: true, value: 1 });
    video.load = () => {
      Reflect.deleteProperty(video, 'seeking');
      Reflect.deleteProperty(video, 'readyState');
      video.dataset.reloads = String(Number(video.dataset.reloads ?? 0) + 1);
      load();
    };
    video.dispatchEvent(new Event('seeking'));
  });
  await page.clock.runFor(7000);
  await expect(front).toHaveCSS('visibility', 'visible');
  await expect(page.locator('.analysis-camera-front [data-camera-state]')).toBeHidden();
  await page.clock.runFor(2000);
  await expect(front).toHaveAttribute('data-reloads', '1');
  await expect
    .poll(() =>
      front.evaluate((video: HTMLVideoElement) =>
        !video.seeking && video.readyState >= 2 ? video.currentTime : -1,
      ),
    )
    .toBeCloseTo(time, 2);
  await expect(plot).toHaveAttribute('aria-valuenow', String(time));
  await expect(page.getByRole('button', { name: 'Play timeline', exact: true })).toBeVisible();
  await expect(page.locator('.recording-errors')).toHaveCount(0);
});
