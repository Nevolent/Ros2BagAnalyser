import { test, expect } from '@playwright/test';

test('recording sorting uses numeric values and preserves selection, filters and original order', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  const rows = page.locator('.bag-table tbody tr:visible');
  const original = await rows.locator('.bag-name').allTextContents();
  const selected = page.getByRole('checkbox', {
    name: `Select ${original[0]}`,
    exact: true,
    includeHidden: true,
  });
  await selected.check();
  const size = page.getByRole('columnheader', { name: 'Size', exact: true });
  await size.getByRole('button').click();
  await expect(size).toHaveAttribute('aria-sort', 'ascending');
  const ascending = await rows.locator('td:nth-child(5)').allTextContents();
  expect(ascending.map(parseFloat)).toEqual(ascending.map(parseFloat).sort((a, b) => a - b));
  await expect(selected).toBeChecked();
  await size.getByRole('button').click();
  await expect(size).toHaveAttribute('aria-sort', 'descending');
  const descending = await rows.locator('td:nth-child(5)').allTextContents();
  expect(descending.map(parseFloat)).toEqual(ascending.map(parseFloat).reverse());
  await size.getByRole('button').click();
  await expect(rows.locator('.bag-name')).toHaveText(original);
  for (const label of ['Name', 'Recorded', 'Duration', 'Health', 'Analysis']) {
    const header = page.getByRole('columnheader', { name: label, exact: true });
    await header.getByRole('button').press('Enter');
    await expect(header).toHaveAttribute('aria-sort', 'ascending');
  }
  await page.getByRole('button', { name: 'Filter by health' }).click();
  await page.getByRole('menuitemradio', { name: 'Damaged', exact: true }).click();
  await expect(rows).toHaveCount(9);
  await expect(rows.locator('.bag-health-cell')).toHaveText(Array(9).fill('Damaged'));
  await expect(page.locator('[data-recordings-count]')).toHaveCount(0);
  await expect(selected).toBeChecked();
});

test('all processing views sort without changing queue priority or enabling history actions', async ({
  page,
}) => {
  await page.goto('/?demo=1#/processing');
  const names = page.locator('.bag-table tbody .bag-name');
  const original = await names.allTextContents();
  const outputs = page.getByRole('columnheader', { name: 'Outputs', exact: true });
  await outputs.getByRole('button').click();
  await expect(names.first()).toHaveText('sensor_sync_validation_2025-12-26_08-30-00.bag');
  await page.getByRole('button', { name: 'Failures', exact: true }).click();
  const failed = page.getByRole('columnheader', { name: 'Failed outputs', exact: true });
  await failed.getByRole('button').click();
  await failed.getByRole('button').click();
  await expect(page.locator('.bag-table tbody tr').first()).toContainText('2 of 3');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await page.getByRole('columnheader', { name: 'Size', exact: true }).getByRole('button').click();
  // MB and GB compare by bytes, not by the displayed numeric prefix.
  await expect(page.locator('.bag-table tbody td:nth-child(4)')).toHaveText([
    '486 MB',
    '842 MB',
    '1.12 GB',
    '1.64 GB',
  ]);
  await expect(page.locator('.bag-table tbody button, .bag-table tbody input')).toHaveCount(0);
  await page.getByRole('button', { name: 'Queue', exact: true }).click();
  await expect(names).toHaveText(original);
});

test('calendar timestamps use the requested format across the workspace', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-22T08:53:00Z') });
  await page.goto('/?demo=1');
  await expect(page.locator('.bag-recorded time').first()).toHaveText('30/12/2025, 10:25');
  for (const value of await page.locator('.bag-recorded time').allTextContents())
    expect(value).toMatch(/^\d{2}\/\d{2}\/\d{4}, \d{2}:\d{2}$/);
  await page.getByRole('button', { name: 'Rescan Archive', exact: true }).click();
  await page.clock.runFor(5000);
  await page.getByRole('button', { name: 'Archive scan history' }).click();
  await expect(page.locator('[data-last-scan-completed]')).toHaveText('22/09/2026, 11:53');
  await page.getByRole('link', { name: 'Analysis', exact: true }).click();
  await expect(page.locator('.recording-info time')).toHaveText('30/12/2025, 10:25');
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  for (const value of await page.locator('.bag-recorded time').allTextContents())
    expect(value).toMatch(/^\d{2}\/\d{2}\/\d{4}, \d{2}:\d{2}$/);
});

test('sidebar label remains mounted and opaque when switching and clicking navigation', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  await page.getByRole('link', { name: 'Recordings', exact: true }).hover();
  const tooltip = page.getByRole('tooltip');
  await expect(tooltip).toHaveCSS('opacity', '1');
  await tooltip.evaluate((element) => element.setAttribute('data-persistent', 'true'));
  for (const name of ['Analysis', 'Processing', 'Recordings']) {
    await page.getByRole('link', { name, exact: true }).click();
    await expect(tooltip).toHaveText(name);
    await expect(tooltip).toHaveAttribute('data-persistent', 'true');
    await expect(tooltip).toHaveCSS('opacity', '1');
  }
  await page.mouse.move(300, 300);
  await expect(tooltip).toHaveCount(0);
});
