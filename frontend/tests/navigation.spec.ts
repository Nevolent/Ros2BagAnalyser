import { test, expect } from '@playwright/test';

test('switching pages keeps the document and sidebar mounted', async ({ page }) => {
  await page.goto('/?demo=1');
  await page.evaluate(() => {
    (window as typeof window & { originalSidebar?: Element | null }).originalSidebar =
      document.querySelector('[data-slot="sidebar"]');
  });
  for (const [label, heading] of [
    ['Analysis', 'Analysis'],
    ['Processing', 'Processing'],
    ['Recordings', 'Recordings'],
    ['Analysis', 'Analysis'],
  ] as const) {
    await page.getByRole('link', { name: label, exact: true }).first().click();
    await expect(page.getByRole('heading', { name: heading, exact: true, level: 1 })).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          document.querySelector('[data-slot="sidebar"]') ===
          (window as typeof window & { originalSidebar?: Element | null }).originalSidebar,
      ),
    ).toBe(true);
    expect(await page.evaluate(() => performance.getEntriesByType('navigation').length)).toBe(1);
  }
  await expect(
    page.getByRole('heading', { name: 'Analysis / bunker_testing_2025-12-30_10-25-00.bag' }),
  ).toHaveCount(0);
  await expect(page.locator('.analysis-workspace [data-component="imu-timeline"]')).toBeVisible();
});
