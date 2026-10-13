import { expect, test } from '@playwright/test';
import { PNG } from 'pngjs';
import { apiFixture, job } from './api-fixture';

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

test('search clear stays visible and resets the controlled recording filter', async ({ page }) => {
  await apiFixture(page);
  await page.goto('/');
  const input = page.getByPlaceholder('Search recordings');
  const clear = input.locator('..').getByRole('button', { name: 'Clear search' });
  await expect(clear).toBeVisible();
  await input.fill('recording-42');
  await expect(page.locator('.bag-table tbody tr:visible')).toHaveCount(1);
  await clear.click();
  await expect(input).toHaveValue('');
  await expect(input).toBeFocused();
  await expect(page.locator('.bag-table tbody tr:visible')).toHaveCount(3);
  await expect(clear).toBeVisible();
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

test('Space after a mouse checkbox selection controls playback without changing selection', async ({
  page,
}) => {
  await apiFixture(page);
  await page.goto('/#/analysis/42');
  const checkbox = page.getByRole('checkbox', { name: 'X axis' });
  await checkbox.check();
  await page.keyboard.press('Space');
  await expect(page.getByRole('button', { name: 'Pause timeline' })).toBeVisible();
  await expect(checkbox).toBeChecked();
  await page.keyboard.press('Space');
  await expect(page.getByRole('button', { name: 'Play timeline' })).toBeVisible();
  await expect(checkbox).toBeChecked();
  // Keyboard focus retains the checkbox's standard accessible Space behavior.
  await checkbox.focus();
  await checkbox.press('Space');
  await expect(checkbox).not.toBeChecked();
});

test('queued and completed outputs list names and individual runtimes', async ({ page }) => {
  const api = await apiFixture(page);
  api.history.push({
    ...job(14, 'imu_series'),
    recording_id: 47,
    state: 'succeeded',
    finished_at: '2026-09-24T10:01:00Z',
    runtime_ms: 5000,
    output_size_bytes: '1024',
  });
  await page.goto('/#/processing');
  await page.locator('.processing-centered-cell .recording-status-diagnostic').hover();
  await expect(page.getByRole('tooltip')).toHaveText('Front-camera previewIMU data bundle');
  await expect(page.getByRole('tooltip')).not.toContainText('queued');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  const row = page.locator('.bag-table tbody tr');
  await row.locator('.processing-history-outputs').hover();
  await expect(page.getByRole('tooltip')).toContainText('Front-camera preview');
  await expect(page.getByRole('tooltip')).toContainText('IMU data bundle');
  await row.locator('td').nth(1).locator('.recording-status-diagnostic').hover();
  await expect(page.getByRole('tooltip')).toContainText('Front-camera preview: 1:05');
  await expect(page.getByRole('tooltip')).toContainText('IMU data bundle: 0:05');
  await expect(page.getByRole('tooltip')).not.toContainText('Total:');
});

test('IMU outliers stay visible and timestamp pauses clear stale values', async ({ page }) => {
  const api = await apiFixture(page);
  const stamps = Array.from(
    { length: 60 },
    (_, i) => 1_000_000_000 + i * 10_000_000 + (i >= 30 ? 6_000_000_000 : 0),
  );
  api.recording.duration_ns = '8000000000';
  api.recording.outputs.find((output) => output.kind === 'imu_series')!.artifact!.coverage_end_ns =
    String(stamps.at(-1));
  api.imu.data.samples = stamps.map((stamp, i) => [
    String(stamp),
    ...Array(6).fill(i === 20 ? 36000 : 10),
  ]);
  const metadata = api.imu.state.artifact;
  metadata.coverage_end_ns = String(stamps.at(-1));
  metadata.delivered_sample_count = '60';
  metadata.series.forEach((series) => {
    series.finite_sample_count = '60';
    series.non_finite_sample_count = '0';
    series.minimum_value = 10;
    series.maximum_value = 36000;
  });
  await page.goto('/#/analysis/42');
  await expect(page.locator('[data-axis-trace="angular_velocity.z"] path')).toHaveAttribute(
    'd',
    /M.*M/,
  );
  await expect(page.locator('.timeline-spike')).toHaveCount(0);
  const plot = page.getByRole('slider');
  await plot.press('ArrowRight');
  await expect(page.locator('[data-axis-value="Z"], [data-axis-value="z"]')).toHaveText('10.000');
  await plot.press('ArrowRight');
  await expect(page.locator('[data-axis-value="Z"], [data-axis-value="z"]')).toHaveText('—');
});
