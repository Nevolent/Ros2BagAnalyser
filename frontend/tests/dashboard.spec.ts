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

test('full rescan dismisses the hover box and shows its label on pointer reentry', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  await page.clock.install();
  const rescan = page.getByRole('button', { name: 'Full rescan', exact: true });
  const before = await rescan.boundingBox();
  expect(before!.y).toBeGreaterThan(900);
  await rescan.hover();
  await page.clock.runFor(100);
  await expect(page.getByRole('tooltip')).toHaveText('Full rescan');
  await rescan.press('Enter');
  const scanning = page.getByRole('button', { name: 'Scanning archive', exact: true });
  await expect(scanning).toHaveAttribute('aria-busy', 'true');
  await expect(scanning).toHaveAttribute('aria-disabled', 'true');
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  await expect(scanning.locator('svg')).toHaveCSS('animation-name', 'archive-rescan-spin');
  expect(await scanning.boundingBox()).toEqual(before);
  await page.mouse.move(300, 300);
  await scanning.hover();
  await page.clock.runFor(100);
  await expect(page.getByRole('tooltip')).toHaveText('Scanning archive');
  await page.mouse.move(300, 300);
  await page.clock.runFor(300);
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  await page.clock.fastForward(5000);
  await expect(rescan).toBeFocused();
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  await expect(rescan).not.toHaveAttribute('aria-busy', 'true');
});

test('mobile navigation rail keeps the main views accessible', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?demo=1');
  await expect(page.getByRole('button', { name: 'Full rescan', exact: true })).toBeInViewport();
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
