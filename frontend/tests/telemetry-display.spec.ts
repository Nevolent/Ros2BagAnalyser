import { expect, test } from '@playwright/test';
import { apiFixture } from './api-fixture';

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
