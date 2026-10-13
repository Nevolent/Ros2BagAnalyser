import { expect, test } from '@playwright/test';
import { apiFixture, job } from './api-fixture';

test('queue and history hovers cover the row height and list only output names, runtimes and sizes', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.active = null;
  api.failures = [];
  api.history = [
    {
      ...job(13),
      recording_id: 47,
      state: 'succeeded',
      finished_at: '2026-09-24T10:01:00Z',
      runtime_ms: 65000,
      output_size_bytes: '2048',
    },
    {
      ...job(14, 'ai_description'),
      recording_id: 47,
      state: 'succeeded',
      finished_at: '2026-09-24T10:02:00Z',
      runtime_ms: 30000,
      output_size_bytes: '512',
    },
  ];
  await page.goto('/#/processing');
  const tooltip = page.getByRole('tooltip').and(page.locator('.recording-diagnostic-tooltip'));
  const row = page.locator('.bag-table tbody tr').first();
  const outputCell = row.locator('td').nth(3);
  await outputCell.hover({ position: { x: 35, y: 2 } });
  await expect(tooltip).toHaveText('Front-camera previewIMU data bundle');
  const box = (await outputCell.boundingBox())!;
  await page.mouse.move(box.x + 35, box.y + box.height - 2);
  await expect(tooltip).toBeVisible();
  await expect(tooltip).not.toContainText('queued');
  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await row.locator('td').nth(3).hover();
  await expect(tooltip).toHaveText('Front-camera previewAI description');
  const runtime = row.locator('td').nth(1);
  await runtime.hover({ position: { x: 15, y: 2 } });
  await expect(tooltip).toHaveText('Front-camera preview: 1:05AI description: 0:30');
  await expect(tooltip).not.toContainText('Total:');
  const runtimeBox = (await runtime.boundingBox())!;
  await page.mouse.move(runtimeBox.x + 15, runtimeBox.y + runtimeBox.height - 2);
  await expect(tooltip).toBeVisible();
  const size = row.locator('td').nth(2);
  await expect(size).toHaveText('2.50 KiB');
  await size.hover({ position: { x: 15, y: 2 } });
  await expect(tooltip).toHaveText('Front-camera preview: 2.00 KiBAI description: 512 B');
  await page.screenshot({ path: test.info().outputPath('history-size-hover.png') });
});
