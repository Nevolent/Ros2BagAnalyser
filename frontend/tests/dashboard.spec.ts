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

test('sidebar settings opens a small full-rescan popup and restores keyboard focus', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  await page.clock.install();
  const settings = page.getByRole('button', { name: 'Settings', exact: true });
  const before = await settings.boundingBox();
  expect(before!.y).toBeGreaterThan(900);
  await settings.press('Enter');
  const popup = page.getByRole('dialog', { name: 'Settings', exact: true });
  const rescan = popup.getByRole('button', { name: 'Do a full rescan', exact: true });
  await expect(rescan).toBeFocused();
  await expect(popup).toBeInViewport();
  expect((await popup.boundingBox())!.x).toBeGreaterThan(before!.x + before!.width);
  await page.keyboard.press('Escape');
  await expect(settings).toBeFocused();
  await settings.click();
  await rescan.click();
  await expect(popup.getByRole('button', { name: 'Rescanning…' })).toBeDisabled();
  expect(await settings.boundingBox()).toEqual(before);
  await page.clock.fastForward(5000);
  await expect(popup).toHaveCount(0);
  await expect(settings).toBeFocused();
  await expect(page.getByRole('button', { name: 'Rescan Archive' })).toHaveCount(0);
});

test('mobile navigation rail keeps the main views accessible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?demo=1');
  await page.getByRole('button', { name: 'Settings', exact: true }).click();
  await expect(page.getByRole('dialog', { name: 'Settings', exact: true })).toBeInViewport();
  await page.keyboard.press('Escape');
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
