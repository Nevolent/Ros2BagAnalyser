import { test, expect } from '@playwright/test';

test('synthetic red statuses show separate source and output diagnostics', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-02T10:00:00Z') });
  await page.goto('/?synthetic=1');
  await page.getByRole('searchbox', { name: 'Search recordings' }).fill('bunker_night_run_03');
  await page.clock.pauseAt(new Date('2026-10-02T10:01:00Z'));
  const row = page.locator('.bag-table tbody tr:visible');
  await expect(row).toHaveCount(1);
  const tooltip = page.getByRole('tooltip').and(page.locator('.recording-diagnostic-tooltip'));
  const damaged = row.getByRole('button', { name: 'Damaged', exact: true });
  const failed = row.getByRole('button', { name: 'Failed', exact: true });
  // Opening and switching diagnostics must work while application timers are paused.
  await damaged.hover();
  await expect(tooltip).toHaveText('source recording is damaged.');
  await failed.hover();
  await expect(tooltip).toHaveCount(1);
  await expect(tooltip).toHaveText('Top-down preview: angular velocity field is absent.');
  const table = (await page.locator('[data-component="recordings-table"]').boundingBox())!;
  await page.screenshot({
    path: test.info().outputPath('status-diagnostic.png'),
    clip: { x: table.x, y: table.y, width: table.width, height: 220 },
  });
  await tooltip.hover();
  await page.clock.runFor(150);
  await expect(tooltip).toHaveCount(1);
  await damaged.focus();
  await expect(tooltip).toHaveCount(1);
  await expect(tooltip).toHaveText('source recording is damaged.');
  await expect(damaged).toHaveAttribute('aria-describedby', (await tooltip.getAttribute('id'))!);
  await page.keyboard.press('Escape');
  await expect(tooltip).toHaveCount(0);
  await damaged.click();
  await expect(tooltip).toHaveCount(1);
  await page
    .locator('.bag-table-scroll')
    .evaluate((element) => element.dispatchEvent(new Event('scroll')));
  await expect(tooltip).toHaveCount(0);
});

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
  await expect(dialog.getByRole('checkbox', { name: 'Go to Processing' })).toBeChecked();
  await dialog.getByRole('checkbox', { name: 'Go to Processing' }).uncheck();
  await dialog.getByRole('button', { name: 'Cancel' }).click();
  await expect(dialog).not.toBeVisible();
  await expect(page.getByRole('button', { name: 'Prepare Selected', exact: true })).toBeFocused();
  await page.getByRole('button', { name: 'Prepare Selected', exact: true }).click();
  await expect(dialog.getByRole('checkbox', { name: 'Go to Processing' })).toBeChecked();
  await dialog.getByRole('checkbox', { name: 'Go to Processing' }).uncheck();
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
  await expect(dialog.getByRole('checkbox', { name: 'Go to Processing' })).toBeChecked();
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
  // The whole header, including its checkbox and rounded corners, covers scrolled rows.
  const head = page.locator('.bag-table thead');
  const headBox = (await head.boundingBox())!;
  const selectAll = (await page
    .getByRole('checkbox', { name: 'Select all visible bags' })
    .boundingBox())!;
  expect(selectAll.y).toBeGreaterThanOrEqual(headBox.y);
  expect(selectAll.y + selectAll.height).toBeLessThanOrEqual(headBox.y + headBox.height);
  expect(
    await head.evaluate((element) => {
      const box = element.getBoundingClientRect();
      return [box.left + 1, box.left + 18, box.right - 1].every((x) =>
        element.contains(document.elementFromPoint(x, box.top + 2)),
      );
    }),
  ).toBe(true);
  await expect(page.locator('.bag-table tbody tr').last()).toBeInViewport();
  await expect(page.locator('.bag-table tbody tr').last().locator('td').last()).toHaveCSS(
    'border-bottom-width',
    '0px',
  );
});

test('actions match dimensions and pointer clicks leave no button outlines', async ({ page }) => {
  await page.goto('/?demo=1');
  await page.locator('.bag-table tbody .bag-checkbox').first().check();
  const prepare = await page.getByRole('button', { name: 'Prepare Selected' }).boundingBox();
  expect(prepare!.height).toBe(30);
  expect(prepare!.width).toBe(150);
  await expect(
    page.locator('.recordings-actions').getByRole('button', { name: /rescan/i }),
  ).toHaveCount(0);
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

test('row edges retain diagnostic hover and checkbox selection targets', async ({ page }) => {
  await page.goto('/?demo=1');
  await page.getByRole('searchbox', { name: 'Search recordings' }).fill('bunker');
  await page.getByRole('button', { name: 'Filter by analysis' }).click();
  await page.getByRole('menuitemradio', { name: 'Failed', exact: true }).click();
  const rows = page.locator('.bag-table tbody tr:visible');
  expect(await rows.count()).toBeGreaterThan(1);
  const tooltip = page.getByRole('tooltip').and(page.locator('.recording-diagnostic-tooltip'));
  for (const row of [rows.nth(0), rows.nth(1)]) {
    const failed = row.getByRole('button', { name: 'Failed', exact: true });
    const cell = (await row.locator('td').last().boundingBox())!;
    const control = (await failed.boundingBox())!;
    expect(control.y).toBeCloseTo(cell.y, 0);
    expect(control.height).toBeGreaterThanOrEqual(cell.height - 1);
    for (const y of [cell.y + 2, cell.y + cell.height - 2]) {
      await page.mouse.move(control.x + control.width / 2, y);
      await expect(tooltip).toBeVisible();
      await expect(failed).toHaveAttribute('aria-describedby', await tooltip.getAttribute('id'));
    }
    const selection = (await row.locator('.bag-select-cell').boundingBox())!;
    const checkbox = row.getByRole('checkbox');
    await page.mouse.click(selection.x + selection.width / 2, selection.y + 2);
    await expect(checkbox).toBeChecked();
    await page.mouse.click(selection.x + selection.width / 2, selection.y + selection.height - 2);
    await expect(checkbox).not.toBeChecked();
  }
  await expect(page.getByRole('heading', { name: 'Recordings', level: 1 })).toBeVisible();
});
