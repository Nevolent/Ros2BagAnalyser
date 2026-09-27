import { test, expect } from '@playwright/test';

test('table header selects visible bags and tracks partial selection', async ({ page }) => {
  await page.goto('/?demo=1');
  const selectAll = page.getByRole('checkbox', { name: 'Select all visible bags' });
  const rows = page.locator('.bag-table tbody tr:visible .bag-checkbox');
  await selectAll.check();
  const total = await rows.count();
  expect(total).toBeGreaterThan(200);
  await expect(page.locator('.bag-table tbody .bag-checkbox:checked')).toHaveCount(211);
  await rows.first().uncheck();
  await expect(selectAll).toHaveJSProperty('indeterminate', true);
  await page.getByRole('searchbox', { name: 'Search recordings' }).fill('lunar');
  await selectAll.uncheck();
  await expect(page.locator('.bag-table tbody .bag-checkbox:checked')).toHaveCount(160);
  await page.goto('/?demo=1#/processing');
  const processingSelectAll = page.getByRole('checkbox', { name: 'Select all queued jobs' });
  await processingSelectAll.check();
  await expect(page.locator('.bag-table tbody tr:visible .bag-checkbox:checked')).toHaveCount(4);
  await page.getByRole('button', { name: 'History' }).click();
  await expect(page.locator('.bag-table input[type="checkbox"]')).toHaveCount(0);
});

const folder = (page: import('@playwright/test').Page, id: string) =>
  page.locator(`[data-folder="${id}"]`);

test('dense tree contains 30 folders and parent selection includes nested recordings', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  await expect(page.locator('[data-folder]')).toHaveCount(30);
  await expect(page.locator('[data-folder-label]')).toHaveText('Recordings');
  await expect(page.locator('.bag-table tbody tr:visible')).toHaveCount(211);
  expect(await folder(page, 'bunker').evaluate((el) => el.getBoundingClientRect().height)).toBe(28);
  await folder(page, 'bunker').click();
  await expect(page.locator('.bag-table tbody tr:visible')).toHaveCount(63);
  await folder(page, 'bunker-december').click();
  await expect(page.locator('[data-folder-label]')).toHaveText(
    'Bunker / Field tests / 2025 / December',
  );
  await expect(page.locator('.bag-table tbody tr:visible')).toHaveCount(19);
  await folder(page, 'shared').click();
  await expect(page.getByText('No recordings in this folder.')).toBeVisible();
  await folder(page, 'bunker').click();
  await expect(page.locator('.bag-table tbody tr:visible')).toHaveCount(63);
  await expect(page.locator('[data-bag-empty]')).toBeHidden();
});

test('folder search finds nested folders without an All files entry', async ({ page }) => {
  await page.goto('/?demo=1');
  await expect(page.locator('[data-folder]')).toHaveCount(30);
  await expect(page.getByRole('heading', { name: 'Folders' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'All files', exact: true })).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Collapse all folders' })).toHaveCount(0);
  await expect(page.locator('.folder-footer,.folder-total')).toHaveCount(0);
  const search = page.getByRole('searchbox', { name: 'Find a folder' });
  await search.fill('December');
  await expect(page.getByRole('treeitem')).toHaveCount(4);
  await expect(folder(page, 'bunker-december')).toBeVisible();
  await folder(page, 'bunker-december').click();
  await page.getByRole('button', { name: 'Clear folder search' }).click();
  await expect(folder(page, 'bunker-december')).toBeVisible();
  await expect(folder(page, 'bunker-december')).toHaveAttribute('aria-selected', 'true');
  await search.fill('not-a-folder');
  await expect(page.getByText('No folders found.')).toBeVisible();
  await search.press('Escape');
  await expect(page.getByRole('treeitem')).toHaveCount(30);
});

test('tree keyboard navigation and disclosure preserve selection', async ({ page }) => {
  await page.goto('/?demo=1');
  await folder(page, 'bunker-december').click();
  await page.getByRole('button', { name: 'Collapse Bunker', exact: true }).click();
  await expect(folder(page, 'bunker-december')).toBeHidden();
  await expect(page.locator('[data-folder-label]')).toHaveText(
    'Bunker / Field tests / 2025 / December',
  );
  await folder(page, 'bunker').press('ArrowRight');
  await folder(page, 'bunker').press('ArrowRight');
  await expect(folder(page, 'bunker-tests')).toBeFocused();
  await page.keyboard.press('ArrowLeft');
  await expect(folder(page, 'bunker-tests')).toHaveAttribute('aria-expanded', 'false');
  await page.keyboard.press('ArrowLeft');
  await expect(folder(page, 'bunker')).toBeFocused();
  await page.keyboard.press('End');
  await expect(folder(page, 'shared-incoming')).toBeFocused();
  await page.keyboard.press('ArrowLeft');
  await expect(folder(page, 'shared')).toBeFocused();
  await page.keyboard.press('ArrowRight');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(folder(page, 'shared-incoming')).toHaveAttribute('aria-selected', 'true');
  await expect(page.locator('[data-folder-label]')).toHaveText('Shared / Incoming');
  await page.keyboard.press('Home');
  await page.keyboard.type('lu');
  await expect(folder(page, 'lunar')).toBeFocused();
  await page.getByRole('button', { name: 'Collapse folders', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Expand folders', exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'Expand folders', exact: true }).click();
  await expect(folder(page, 'shared-incoming')).toHaveAttribute('aria-selected', 'true');
});

test('folder selection combines with recording filters', async ({ page }) => {
  await page.goto('/?demo=1');
  await folder(page, 'bunker').click();
  await page.getByRole('button', { name: 'Filter by analysis' }).click();
  await page.getByRole('menuitemradio', { name: 'Not planned', exact: true }).click();
  await expect(page.locator('.bag-table tbody tr:visible')).toHaveCount(19);
  await page
    .getByRole('searchbox', { name: 'Search recordings' })
    .fill('bunker_lidar_mapping_run_03');
  await expect(page.locator('.bag-table tbody tr:visible')).toHaveCount(1);
  await page.getByRole('searchbox', { name: 'Search recordings' }).fill('missing-recording');
  await expect(page.getByText('No recordings match your filters.')).toBeVisible();
});

for (const width of [390, 640, 768, 1024, 1440, 1920]) {
  test(`folder tree stays scrollable within a ${width}px viewport`, async ({ page }) => {
    const errors: string[] = [];
    page.on('pageerror', (error) => errors.push(error.message));
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/?demo=1');
    // Expand every branch to exercise all 30 folders, not just the initial tree.
    while (await page.locator('[data-folder][aria-expanded="false"]:visible').count()) {
      await page.locator('[data-folder][aria-expanded="false"]:visible button').first().click();
    }
    await expect(page.getByRole('treeitem')).toHaveCount(30);
    await folder(page, 'shared-incoming').click();
    await expect(page.getByRole('searchbox', { name: 'Find a folder' })).toBeInViewport();
    const geometry = await page.evaluate(() => {
      const tree = document.querySelector('.folder-list')!;
      const panel = document.querySelector('.folder-card')!.getBoundingClientRect();
      const recordings = document
        .querySelector('[data-component="recordings-table"]')!
        .getBoundingClientRect();
      return {
        fits:
          document.documentElement.scrollWidth <= innerWidth &&
          document.documentElement.scrollHeight <= innerHeight,
        scrollable: tree.scrollHeight > tree.clientHeight,
        panelBottom: panel.bottom,
        recordingsTop: recordings.top,
      };
    });
    expect(geometry.fits).toBe(true);
    expect(geometry.scrollable).toBe(true);
    if (width <= 600) expect(geometry.panelBottom).toBeLessThan(geometry.recordingsTop);
    expect(errors).toEqual([]);
  });
}
