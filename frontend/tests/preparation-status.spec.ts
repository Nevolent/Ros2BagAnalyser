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
        ],
      },
    });
  });
}
