import { test, expect } from '@playwright/test';

test('React preserves the timeline across shell updates and cleans up every page', async ({
  page,
}) => {
  const errors: string[] = [];
  const external: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('console', (message) => {
    if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text());
  });
  page.on('request', (request) => {
    if (new URL(request.url()).hostname !== '127.0.0.1') external.push(request.url());
  });
  await page.goto('/#/analysis');
  const timeline = page.getByRole('slider', { name: 'Recording timeline' });
  await timeline.focus();
  await timeline.press('ArrowRight');
  const time = await timeline.getAttribute('aria-valuenow');
  await page.keyboard.press('Control+k');
  await expect(page.getByRole('dialog', { name: 'Search' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(timeline).toHaveAttribute('aria-valuenow', time!);
  for (const route of ['Processing', 'Recordings', 'Analysis', 'Processing', 'Recordings']) {
    await page.getByRole('link', { name: route, exact: true }).click();
    await expect(page.getByRole('heading', { name: route, exact: true, level: 1 })).toBeVisible();
    await expect(page.locator('dialog[open], .ui-portal, .bag-filter-menu')).toHaveCount(0);
  }
  expect(errors).toEqual([]);
  expect(external).toEqual([]);
});

test('legacy entry URLs and browser history retain the mounted shell', async ({ page }) => {
  await page.goto('/#/workflows');
  await expect(page).toHaveURL(/#\/analysis$/);
  await expect(
    page.getByRole('heading', { name: 'Analysis', exact: true, level: 1 }),
  ).toBeVisible();
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await page.goBack();
  await expect(
    page.getByRole('heading', { name: 'Analysis', exact: true, level: 1 }),
  ).toBeVisible();
  await page.goForward();
  await expect(
    page.getByRole('heading', { name: 'Processing', exact: true, level: 1 }),
  ).toBeVisible();
  expect(await page.evaluate(() => performance.getEntriesByType('navigation').length)).toBe(1);
});
