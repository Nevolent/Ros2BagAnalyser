import { expect, test } from '@playwright/test';
import { apiFixture } from './api-fixture';

test('telemetry streams valid JSON above the former 64 MiB limit', async ({ page }) => {
  test.setTimeout(60_000);
  const api = await apiFixture(page);
  const body = JSON.stringify(api.imu.data) + ' '.repeat(64 * 1024 * 1024);
  const size = String(Buffer.byteLength(body));
  api.recording.outputs.find((output) => output.kind === 'imu_series')!.artifact!.size_bytes = size;
  api.imu.state.artifact.size_bytes = size;
  await page.route('**/api/recordings/42/imu-series/data/3', (route) =>
    route.fulfill({ contentType: 'application/json', body }),
  );
  await page.goto('/#/analysis/42');
  await expect(page.locator('[data-axis-trace] path')).toHaveAttribute('d', /M/, {
    timeout: 30_000,
  });
});

test('telemetry rejects metadata exceeding the new bound before fetching data', async ({
  page,
}) => {
  const api = await apiFixture(page);
  const artifact = api.recording.outputs.find((output) => output.kind === 'imu_series')!.artifact!;
  artifact.size_bytes = String(256 * 1024 * 1024 + 1);
  api.imu.state.artifact.size_bytes = artifact.size_bytes;
  await page.goto('/');
  const message = await page.evaluate(async (expected) => {
    const modulePath = '/src/data/telemetry.ts';
    const { loadTelemetry } = await import(modulePath);
    try {
      await loadTelemetry(42, expected, new AbortController().signal);
      return null;
    } catch (error) {
      return (error as Error).message;
    }
  }, artifact);
  expect(message).toBe('IMU data exceeds the 256 MiB limit.');
});

test('IMU traces stop at measured endpoints and disappear in views before and after coverage', async ({
  page,
}) => {
  await apiFixture(page);
  await page.goto('/#/analysis/42');
  const trace = page.locator('[data-axis-trace] path');
  await expect(trace).toHaveAttribute('d', /M/);
  const plot = page.getByRole('slider');
  const width = (await plot.boundingBox())!.width;
  const coordinates = (await trace.getAttribute('d'))!
    .match(/[ML]([\d.-]+),/g)!
    .map((point) => Number(point.slice(1, -1)));
  expect(Math.min(...coordinates)).toBeCloseTo(width / 6, 2);
  expect(Math.max(...coordinates)).toBeCloseTo((width * 4) / 6, 2);
  await expect(page.locator('[data-timeline-single-sample]')).toHaveCount(1);
  for (let i = 0; i < 3; i++)
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await expect(trace).toHaveAttribute('d', '');
  await expect(page.locator('[data-timeline-single-sample]')).toHaveCount(0);
  await expect(page.locator('[data-axis-value]')).toHaveText('—');
  await plot.press('End');
  await expect(trace).toHaveAttribute('d', '');
  await expect(page.locator('[data-timeline-single-sample]')).toHaveCount(0);
  await expect(page.locator('[data-axis-value]')).toHaveText('—');
  await page.getByRole('button', { name: 'Reset zoom', exact: true }).click();
  await expect(trace).toHaveAttribute('d', /M/);
});

for (const width of [390, 1440]) {
  test(`long Analysis diagnostics wrap completely at ${width}px`, async ({ page }) => {
    const api = await apiFixture(page);
    const message =
      'Sensor stream could not be processed: ' +
      'very_long_diagnostic_detail_'.repeat(20) +
      '<img src=x onerror=alert(1)> End of diagnostic.';
    api.recording.diagnostic = { code: 'custom_sensor_failure', message };
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/#/analysis/42');
    const error = page
      .getByRole('region', { name: 'Recording errors' })
      .getByText(message, { exact: true });
    await expect(error).toBeAttached();
    await expect(error).toHaveCSS('white-space', 'normal');
    await expect(error).toHaveCSS('overflow-wrap', 'anywhere');
    const bounds = await error.evaluate((el) => ({
      height: el.getBoundingClientRect().height,
      visibleWidth: el.clientWidth,
      contentWidth: el.scrollWidth,
      visibleHeight: el.clientHeight,
      contentHeight: el.scrollHeight,
    }));
    expect(bounds.height).toBeGreaterThan(36);
    expect(bounds.contentWidth).toBeLessThanOrEqual(bounds.visibleWidth);
    expect(bounds.contentHeight).toBeLessThanOrEqual(bounds.visibleHeight);
    await expect(page.locator('.recording-errors img, .recording-errors script')).toHaveCount(0);
  });
}
