import { test, expect } from '@playwright/test';

test('folder totals, failed filters and empty states reflect the archive', async ({ page }) => {
  await page.goto('/?demo=1');
  await page.locator('[data-folder="bunker"]').click();
  await expect(page.locator('[data-folder="bunker"] .folder-bag-count')).toHaveText('63');
  await page.getByRole('button', { name: 'Filter by analysis' }).click();
  await page.getByRole('menuitemradio', { name: 'Failed', exact: true }).click();
  const visible = page.locator('.bag-table tbody tr:visible');
  await expect(visible).toHaveCount(8);
  await expect(visible.first().locator('td').last()).toHaveText('Failed');
  await expect(visible.last().locator('td').last()).toHaveCSS('border-bottom-width', '0px');
  // Parent counts remain archive totals when a recording filter is active.
  await expect(page.locator('[data-folder="bunker"] .folder-bag-count')).toHaveText('63');
  await page.getByRole('button', { name: 'Filter by analysis' }).click();
  await page.getByRole('menuitemradio', { name: 'Analysis', exact: true }).click();
  await page.locator('[data-folder="shared"]').click();
  await expect(page.getByText('No recordings in this folder.')).toBeVisible();
  await expect(page.getByText('Select another folder.', { exact: true })).toBeVisible();
  await expect(page.getByText(/return to All files/)).toHaveCount(0);
  const centered = await page.locator('.bag-empty').evaluate((el) => {
    const region = el.getBoundingClientRect();
    const text = el.querySelector('p')!.getBoundingClientRect();
    const detail = el.querySelector('span')!.getBoundingClientRect();
    return Math.abs((region.top + region.bottom) / 2 - (text.top + detail.bottom) / 2);
  });
  expect(centered).toBeLessThan(2);
});

test('preparation includes selected bags hidden by filters and supports cancel or confirm', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  const first = 'bunker_testing_2025-12-30_10-25-00.bag';
  const second = 'lunar_testing_low_light_2025-12-29_14-10-00.bag';
  await page.getByRole('checkbox', { name: `Select ${first}`, exact: true }).check();
  await page.getByRole('checkbox', { name: `Select ${second}`, exact: true }).check();
  await page.locator('[data-folder="bunker"]').click();
  await page.getByRole('button', { name: 'Prepare Selected', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Prepare recordings', exact: true });
  await expect(dialog.getByRole('listitem')).toHaveText([first, second]);
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Prepare Selected', exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'Prepare Selected', exact: true }).click();
  await dialog.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('heading', { name: 'Recordings', level: 1 })).toBeVisible();
  await expect(page.getByRole('status')).toContainText('Preparation request completed.');
  await expect(page.locator('.bag-checkbox:checked')).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Prepare Selected', exact: true })).toBeHidden();
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await expect(page.locator('.bag-table tbody tr:visible .bag-name')).toContainText([
    first,
    second,
  ]);
  await page.getByRole('link', { name: 'Recordings', exact: true }).click();
  await expect(
    page.locator('.bag-table tbody tr').filter({ hasText: first }).locator('td').last(),
  ).toHaveText('Queued');
});

test('confirming a mock bag opens Processing and lists the queued recording', async ({ page }) => {
  await page.goto('/?demo=1');
  const name = 'bunker_field_test_07_2025-12-18_14-49-00.bag';
  await page.getByRole('searchbox', { name: 'Search recordings' }).fill(name);
  await page.getByRole('checkbox', { name: `Select ${name}`, exact: true }).check();
  await page.getByRole('button', { name: 'Prepare Selected' }).click();
  const dialog = page.getByRole('dialog', { name: 'Prepare recordings' });
  await dialog.getByRole('checkbox', { name: 'Go to Processing' }).check();
  await dialog.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page).toHaveURL(/#\/processing$/);
  await expect(
    page.locator('.bag-table tbody tr:visible .bag-name').filter({ hasText: name }),
  ).toBeVisible();
});

test('scrolling keeps filters and headers visible without shifting table columns', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  const search = page.getByRole('searchbox', { name: 'Search recordings' });
  const nameHeader = page.getByRole('columnheader', { name: 'Name', exact: true });
  const before = await nameHeader.boundingBox();
  const viewport = page.locator('.recordings-table-body .bag-table-scroll');
  const track = page.locator('.recordings-table-body .scrollbar-track');
  const thumb = page.locator('.recordings-table-body .scrollbar-thumb');
  await expect(track).toHaveAttribute('data-visible', 'true');
  const headerBox = await nameHeader.boundingBox();
  const trackBefore = await track.boundingBox();
  expect(trackBefore!.y).toBeGreaterThan(headerBox!.y + headerBox!.height);
  const thumbBefore = await thumb.boundingBox();
  await search.fill('sensor_sync_validation');
  const filtered = await nameHeader.boundingBox();
  expect(filtered!.x).toBe(before!.x);
  expect(filtered!.width).toBe(before!.width);
  await expect(track).toHaveAttribute('data-visible', 'false');
  await search.clear();
  await viewport.hover();
  await page.mouse.wheel(0, 700);
  await expect.poll(async () => viewport.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  const thumbAtScroll = (await thumb.boundingBox())!;
  const trackAfterScroll = (await track.boundingBox())!;
  await page.mouse.move(
    thumbAtScroll.x + thumbAtScroll.width / 2,
    thumbAtScroll.y + thumbAtScroll.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    thumbAtScroll.x + thumbAtScroll.width / 2,
    trackAfterScroll.y + trackAfterScroll.height - thumbAtScroll.height / 2,
    { steps: 6 },
  );
  await page.mouse.up();
  await expect.poll(async () => viewport.evaluate((el) => el.scrollTop)).toBeGreaterThan(700);
  await expect.poll(async () => (await thumb.boundingBox())?.y).toBeGreaterThan(thumbBefore!.y);
  await expect(search).toBeInViewport();
  await expect(nameHeader).toBeInViewport();
  await expect(page.locator('.bag-table tbody tr').last()).toBeInViewport();
  await expect(page.locator('.bag-table tbody tr').last().locator('td').last()).toHaveCSS(
    'border-bottom-width',
    '0px',
  );
});

test('actions match dimensions and pointer clicks leave no button outlines', async ({ page }) => {
  await page.goto('/?demo=1');
  await page.locator('.bag-table tbody .bag-checkbox').first().check();
  const scan = await page.locator('.recordings-rescan').boundingBox();
  const prepare = await page.getByRole('button', { name: 'Prepare Selected' }).boundingBox();
  expect(prepare!.height).toBe(scan!.height);
  expect(prepare!.width).toBe(scan!.width);
  const rescanButton = (await page
    .getByRole('button', { name: 'Rescan Archive', exact: true })
    .boundingBox())!;
  const historyButton = (await page
    .getByRole('button', { name: 'Archive scan history', exact: true })
    .boundingBox())!;
  expect(historyButton.x - rescanButton.x - rescanButton.width).toBe(1);
  await expect(page.locator('.recordings-rescan')).toHaveCSS(
    'background-color',
    'rgba(0, 0, 0, 0)',
  );
  await page.getByRole('button', { name: 'Collapse folders', exact: true }).click();
  const reopen = page.getByRole('button', { name: 'Expand folders', exact: true });
  await expect(reopen).toHaveCSS('outline-style', 'none');
  await expect(reopen).toHaveCSS('box-shadow', 'none');
  await reopen.click();
  for (const label of ['Find a folder', 'Search recordings']) {
    const input = page.getByRole('searchbox', { name: label });
    await input.click();
    expect(
      await input.evaluate((el) => getComputedStyle(el.parentElement!).borderTopColor),
    ).not.toBe('rgba(0, 0, 0, 0)');
  }
});

test('large preparation lists stay usable on a phone and Escape preserves selection', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/?demo=1');
  await page.getByRole('checkbox', { name: 'Select all visible bags' }).check();
  await page.getByRole('button', { name: 'Prepare Selected' }).click();
  const dialog = page.getByRole('dialog', { name: 'Prepare recordings' });
  await expect(dialog.getByRole('listitem')).toHaveCount(211);
  await expect(dialog.getByRole('button', { name: 'Confirm', exact: true })).toBeInViewport();
  await expect(dialog.getByRole('checkbox', { name: 'Go to Processing' })).toBeInViewport();
  await page.keyboard.press('Escape');
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Prepare Selected' })).toBeFocused();
  await expect(page.locator('.bag-table tbody .bag-checkbox:checked')).toHaveCount(211);
});
