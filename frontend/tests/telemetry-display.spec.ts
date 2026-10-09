import { expect, test } from '@playwright/test';
import { apiFixture } from './api-fixture';

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
