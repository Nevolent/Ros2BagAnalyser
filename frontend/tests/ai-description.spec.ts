import { test, expect } from '@playwright/test';
import { apiFixture } from './api-fixture';

test('Details renders the description as text and shows only a true bunker tag', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.recording.ai_description = {
    description: '<img src=x onerror=alert(1)> An indoor area. No people are visible.',
    bunker: true,
  };
  await page.goto('/#/analysis/42');
  const section = page.getByRole('region', { name: 'AI description', exact: true });
  await expect(section).toContainText(api.recording.ai_description.description);
  await expect(section.locator('img')).toHaveCount(0);
  const tag = section.getByText('Bunker', { exact: true });
  await expect(tag).toBeVisible();
  await expect(tag).toHaveCSS('border-radius', '4px');
  const mutedColor = await page
    .locator('.recording-info dt')
    .first()
    .evaluate((el) => getComputedStyle(el).color);
  await expect(section.locator('p')).toHaveCSS('color', mutedColor);
  api.recording.diagnostic = { code: 'synthetic_warning', message: 'A diagnostic to inspect.' };
  const errors = page.getByRole('region', { name: 'Recording errors', exact: true });
  await expect(errors).toContainText('A diagnostic to inspect.');
  expect(await errors.evaluate((el) => el.previousElementSibling?.getAttribute('aria-label'))).toBe(
    'AI description',
  );
  expect(await errors.evaluate((el) => el.nextElementSibling)).toBeNull();
  await expect(page.getByText('ROS database', { exact: true })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Source components' })).toContainText('Rosbag');
  await page
    .locator('.recording-details-panel')
    .screenshot({ path: test.info().outputPath('description-panel.png') });
  await expect(page.getByRole('region', { name: 'Analysis outputs' })).not.toContainText(
    'AI description',
  );
  expect(
    await section.evaluate((el) => el.previousElementSibling?.getAttribute('aria-label')),
  ).toBe('Source components');
  api.recording.ai_description.bunker = false;
  await expect(section.getByText('Bunker', { exact: true })).toHaveCount(0);
  await expect(section).toContainText(api.recording.ai_description.description);
  await page.getByRole('button', { name: 'Topics', exact: true }).click();
  await expect(section).toHaveCount(0);
});

for (const width of [1440, 390]) {
  test(`Partially prepared filter fits matching controls and prepares all visible recordings at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    const api = await apiFixture(page);
    api.recording.outputs[3] = { kind: 'ai_description', state: 'not_requested', diagnostic: null };
    api.recording.ai_description = null;
    api.recording.analysis_state = 'partially_prepared';
    await page.goto('/');
    const filter = page.getByRole('button', { name: 'Filter by analysis' });
    await filter.click();
    await page.getByRole('menuitemradio', { name: 'Partially prepared', exact: true }).click();
    await expect(filter).toHaveText('Partially prepared');
    await expect(filter).toBeFocused();
    const rows = page.locator('.bag-table tbody tr:visible');
    await expect(rows).toHaveCount(2);
    const health = page.getByRole('button', { name: 'Filter by health' });
    const widths = await Promise.all(
      [health, filter].map((control) => control.evaluate((el) => el.getBoundingClientRect().width)),
    );
    expect(widths[0]).toBeCloseTo(widths[1], 1);
    expect(widths[1]).toBeLessThanOrEqual(140);
    const labelFits = await filter.evaluate((el) => {
      const range = document.createRange();
      range.selectNodeContents(el.firstChild!);
      const label = range.getBoundingClientRect();
      const icon = el.querySelector('svg')!.getBoundingClientRect();
      return icon.left - label.right;
    });
    expect(labelFits).toBeGreaterThanOrEqual(4);
    await expect(
      rows.first().locator('.status-success').filter({ hasText: 'Partially prepared' }),
    ).toBeVisible();
    await expect(page.locator('.bag-health-column')).toHaveCSS('width', '112px');
    expect(await filter.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
    if (width === 1440)
      await page.screenshot({ path: test.info().outputPath('partial-filter.png') });
    await page.getByRole('checkbox', { name: 'Select all visible bags' }).check();
    await page.getByRole('button', { name: 'Prepare Selected', exact: true }).click();
    await page.getByRole('dialog').getByRole('button', { name: 'Confirm', exact: true }).click();
    await expect.poll(() => api.posts.length).toBe(1);
    expect(api.posts[0].body).toEqual({
      recording_ids: [42, 44],
      output_kinds: [
        'front_preview',
        'ai_description',
        'topdown_preview',
        'imu_series',
        'encoder_series',
        'thumbnail',
      ],
    });
  });
}

test('A missing or queued description shows a truthful muted state', async ({ page }) => {
  const api = await apiFixture(page);
  api.recording.outputs[3] = { kind: 'ai_description', state: 'not_requested', diagnostic: null };
  api.recording.ai_description = null;
  await page.goto('/#/analysis/42');
  const section = page.getByRole('region', { name: 'AI description', exact: true });
  await expect(section).toHaveText('AI description not prepared.');
  api.recording.outputs[3].state = 'queued';
  await expect(section).toHaveText('AI description: This is currently queued.');
  await expect(section.getByText('Bunker', { exact: true })).toHaveCount(0);
});
