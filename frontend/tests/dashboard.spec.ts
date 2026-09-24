import { test, expect } from '@playwright/test';

test('search supports filtering, empty states, shortcuts and keyboard navigation', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  await page.keyboard.press('Control+k');
  const dialog = page.getByRole('dialog', { name: 'Search' });
  await expect(dialog).toBeVisible();
  await page.getByRole('combobox').fill('contacts');
  await expect(dialog.getByRole('option')).toHaveCount(1);
  await page.getByRole('combobox').press('Enter');
  await expect(page).toHaveURL(/#\/contacts$/);
  await expect(dialog).not.toBeVisible();
  await page.keyboard.press('Control+k');
  await page.getByRole('combobox').fill('does-not-exist');
  await expect(page.getByText('No results found.')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('link', { name: 'Tectrace home' })).toBeFocused();
});

test('archive scan controls stay aligned and history updates after a scan', async ({ page }) => {
  await page.goto('/?demo=1');
  await page.clock.install();
  const rescan = page.getByRole('button', { name: 'Rescan Archive', exact: true });
  const before = await page.locator('.recordings-rescan').boundingBox();
  await rescan.click();
  await expect(page.getByRole('button', { name: 'Scanning archive', exact: true })).toBeDisabled();
  const during = await page.locator('.recordings-rescan').boundingBox();
  expect(during).toEqual(before);
  await page.getByRole('button', { name: 'Archive scan history' }).click();
  const scanHistory = page.getByRole('dialog', { name: 'Scan history', exact: true });
  await expect(scanHistory.getByText('Last scan completed')).toBeVisible();
  await expect(scanHistory.getByText('Not scanned yet')).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Archive scan history' })).toBeFocused();
  await page.clock.fastForward(5000);
  await expect(rescan).toBeEnabled();
  await page.getByRole('button', { name: 'Archive scan history' }).click();
  await expect(scanHistory.getByText('Not scanned yet')).toHaveCount(0);
  await expect(scanHistory.locator('dd')).not.toBeEmpty();
});

test('mobile navigation rail keeps the main views accessible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?demo=1');
  for (const label of ['Analysis', 'Processing', 'Recordings']) {
    const link = page.getByRole('link', { name: label, exact: true });
    await expect(link).toBeInViewport();
    await link.click();
    await expect(page.getByRole('heading', { name: label, level: 1, exact: true })).toBeVisible();
    await expect(link).toHaveAttribute('aria-current', 'page');
  }
});

for (const width of [390, 640, 768, 1024, 1440, 1920])
  test(`responsive layout fits ${width}px`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/?demo=1');
    await expect(page.locator('[data-component="recordings-table"]')).toBeVisible();
    await expect(page.getByRole('navigation', { name: 'Browse folders' })).toBeVisible();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <= innerWidth &&
          document.documentElement.scrollHeight <= innerHeight,
      ),
    ).toBe(true);
    expect(errors).toEqual([]);
  });
