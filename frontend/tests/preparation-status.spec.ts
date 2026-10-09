import { test, expect } from '@playwright/test';
import { apiFixture } from './api-fixture';

for (const missing of ['camera', 'encoders'] as const) {
  test(`reusable outputs remain partially prepared when ${missing} need preparation`, async ({
    page,
  }) => {
    const api = await apiFixture(page);
    api.recording.analysis_state = 'partially_prepared';
    if (missing === 'camera') {
      api.recording.outputs = api.recording.outputs.map((output) =>
        ['front_preview', 'ai_description'].includes(output.kind)
          ? { kind: output.kind, state: 'not_requested', diagnostic: null }
          : output,
      );
    } else {
      api.recording.outputs.push({
        kind: 'encoder_series',
        state: 'not_requested',
        diagnostic: null,
      });
    }
    api.catalog.recordings = [api.recording];

    await page.goto('/');
    const rows = page.locator('.bag-table tbody tr:visible');
    await expect(rows).toHaveCount(1);
    await expect(rows.getByText('Partially prepared', { exact: true })).toBeVisible();
    await expect(rows.getByText('Ready', { exact: true })).toHaveCount(0);
    await expect(rows.getByText('Not planned', { exact: true })).toHaveCount(0);
    const status = rows.getByRole('button', { name: 'Partially prepared', exact: true });
    await status.hover();
    const tooltip = page.getByRole('tooltip');
    const pending = tooltip.locator('[data-output-state=pending]');
    await expect(pending).toContainText(
      missing === 'camera'
        ? ['Front-camera preview', 'AI description']
        : ['Wheel encoder data bundle'],
    );
    await expect(tooltip).not.toContainText('Not prepared');
    const prepared = tooltip.locator('[data-output-state=ready]');
    await expect(prepared.filter({ hasText: 'IMU data bundle' })).toBeVisible();
    expect(await prepared.first().evaluate((el) => getComputedStyle(el).color)).toBe(
      await status.evaluate((el) => getComputedStyle(el).color),
    );
    await expect(pending.first()).toHaveClass('status-muted');
    expect(await pending.first().evaluate((el) => getComputedStyle(el).color)).not.toBe(
      await prepared.first().evaluate((el) => getComputedStyle(el).color),
    );
    await status.focus();
    await status.press('Escape');
    await expect(tooltip).toHaveCount(0);
    await page.getByRole('button', { name: 'Filter by analysis' }).click();
    await page.getByRole('menuitemradio', { name: 'Partially prepared', exact: true }).click();
    await expect(rows).toHaveCount(1);
    await page.getByRole('checkbox', { name: 'Select all visible bags' }).check();
    await page.getByRole('button', { name: 'Prepare Selected', exact: true }).click();
    const dialog = page.getByRole('dialog', { name: 'Prepare recordings' });
    await dialog.getByRole('checkbox', { name: 'Go to Processing' }).uncheck();
    await dialog.getByRole('button', { name: 'Confirm', exact: true }).click();
    await expect.poll(() => api.posts.length).toBe(1);
    expect(api.posts[0]).toEqual({
      path: '/api/v1/recordings/prepare',
      body: {
        recording_ids: [42],
        output_kinds: [
          'front_preview',
          'ai_description',
          'topdown_preview',
          'imu_series',
          'encoder_series',
          'thumbnail',
        ],
      },
    });
  });
}

test('preparation hover omits unavailable inputs and uses grey for available pending outputs', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.recording.analysis_state = 'partially_prepared';
  api.recording.outputs = api.recording.outputs.map((output) =>
    output.kind === 'topdown_preview'
      ? {
          kind: output.kind,
          state: 'unavailable',
          diagnostic: { code: 'topdown_video_unavailable', message: 'No top-down video.' },
        }
      : output,
  );
  api.recording.outputs.push({ kind: 'encoder_series', state: 'not_requested', diagnostic: null });
  api.catalog.recordings = [api.recording];
  await page.goto('/');
  const status = page.getByRole('button', { name: 'Partially prepared', exact: true });
  await status.focus();
  const tooltip = page.getByRole('tooltip');
  await expect(tooltip.locator('[data-output-state=unavailable]')).toHaveCount(0);
  await expect(tooltip).not.toContainText('Top-down preview');
  await expect(tooltip).not.toContainText('Unavailable');
  await expect(tooltip.locator('[data-output-state=pending]')).toContainText(
    'Wheel encoder data bundle',
  );
  await expect(tooltip.locator('[data-output-state=pending]')).toHaveClass('status-muted');
  await expect(tooltip.locator('[data-output-state=ready]').first()).toHaveClass('status-success');
  await expect(tooltip.locator('[data-output-state=ready]')).toHaveCount(3);
  await expect(tooltip).not.toContainText('Not prepared');
  await tooltip.screenshot({ path: test.info().outputPath('preparation-outputs.png') });
  await status.press('Escape');
  await expect(tooltip).toHaveCount(0);
});
