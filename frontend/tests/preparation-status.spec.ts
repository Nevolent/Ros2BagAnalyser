import { test, expect } from '@playwright/test';
import { apiFixture, diagnostic } from './api-fixture';

for (const kind of ['ai_description', 'front_preview'] as const) {
  test(`failed ${kind} marks the recording Failed and preserves ready siblings and diagnostics`, async ({
    page,
  }) => {
    const api = await apiFixture(page);
    api.recording.analysis_state = 'failed';
    api.recording.outputs = api.recording.outputs.filter((output) => output.kind !== kind);
    api.recording.outputs.push({ kind, state: 'failed', diagnostic });
    api.recording.outputs.push({
      kind: 'thumbnail',
      state: 'failed',
      diagnostic: { code: 'thumbnail_processing_failed', message: 'Separate thumbnail failure.' },
    });
    api.catalog.recordings = [api.recording];
    await page.goto('/');
    const status = page.getByRole('button', { name: 'Failed', exact: true });
    await expect(status).toBeVisible();
    await expect(status).toHaveClass(/status-error/);
    await expect(
      page.locator('.bag-table').getByText('Partially prepared', { exact: true }),
    ).toHaveCount(0);
    await status.focus();
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip.locator('[data-output-state=ready]')).not.toHaveCount(0);
    await expect(tooltip).toContainText('<script>not markup</script> Output failed.');
    await expect(tooltip.locator('script')).toHaveCount(0);
    await expect(tooltip.locator('.status-error')).toContainText('Output failed.');
    await expect(tooltip).not.toContainText('Thumbnail');
    await expect(tooltip).not.toContainText('Separate thumbnail failure.');
    await status.press('Escape');
    await expect(tooltip).toHaveCount(0);
    await page.getByRole('button', { name: 'Filter by analysis' }).click();
    await page.getByRole('menuitemradio', { name: 'Failed', exact: true }).click();
    await expect(page.locator('.bag-table tbody tr:visible')).toHaveCount(1);
  });
}

for (const analysis of ['ready', 'partially_prepared'] as const) {
  for (const thumbnailState of ['ready', 'not_requested', 'failed'] as const) {
    test(`${analysis} hover excludes ${thumbnailState} thumbnail output and diagnostics`, async ({
      page,
    }) => {
      const api = await apiFixture(page);
      api.recording.analysis_state = analysis;
      if (analysis === 'partially_prepared') {
        api.recording.outputs.push({
          kind: 'encoder_series',
          state: 'not_requested',
          diagnostic: null,
        });
      }
      api.recording.outputs.push({
        kind: 'thumbnail',
        state: thumbnailState,
        diagnostic: {
          code: 'thumbnail_processing_failed',
          message: 'Separate thumbnail failure.',
        },
      });
      api.failures = [
        {
          ...api.failures[0],
          recording_id: api.recording.id,
          kind: 'thumbnail',
          diagnostic: {
            code: 'thumbnail_processing_failed',
            message: 'Separate thumbnail failure.',
          },
        },
      ];
      api.catalog.recordings = [api.recording];
      await page.goto('/');
      const status = page.getByRole('button', {
        name: analysis === 'ready' ? 'Ready' : 'Partially prepared',
        exact: true,
      });
      await status.focus();
      const tooltip = page.getByRole('tooltip');
      await expect(tooltip.locator('[data-output-state]')).toHaveCount(
        analysis === 'ready' ? 4 : 5,
      );
      await expect(tooltip).not.toContainText('Thumbnail');
      await expect(tooltip).not.toContainText('Separate thumbnail failure.');
      await expect(tooltip.locator('.status-error')).toHaveCount(0);
      await status.press('Escape');
      await expect(tooltip).toHaveCount(0);
      if (thumbnailState === 'failed') {
        await page.locator('.recording-thumbnail').hover();
        await expect(page.locator('.recording-thumbnail')).toHaveText('No Thumbnail');
        await expect(tooltip).toHaveCount(0);
        await page.locator('.recording-thumbnail').click();
        await expect(page.getByRole('region', { name: 'Recording errors' })).toContainText(
          'Separate thumbnail failure.',
        );
      }
    });
  }
}

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
    await expect(tooltip.locator('[data-output-state]')).toContainText([
      'Front-camera preview',
      'Top-down preview',
      'IMU data bundle',
      'AI description',
      ...(missing === 'encoders' ? ['Wheel encoder data bundle'] : []),
    ]);
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

test('Ready shows the actual prepared outputs on hover and keyboard focus', async ({ page }) => {
  const api = await apiFixture(page);
  api.recording.analysis_state = 'ready';
  api.catalog.recordings = [api.recording];
  await page.goto('/');
  const status = page.getByRole('button', { name: 'Ready', exact: true });
  await status.hover();
  const tooltip = page.getByRole('tooltip');
  await expect(tooltip.locator('p')).toHaveCount(4);
  await expect(tooltip.locator('[data-output-state=ready]')).toContainText([
    'Front-camera preview',
    'Top-down preview',
    'IMU data bundle',
    'AI description',
  ]);
  await expect(tooltip.locator('[data-output-state=pending]')).toHaveCount(0);
  await expect(tooltip.locator('p')).toHaveClass([
    'status-success',
    'status-success',
    'status-success',
    'status-success',
  ]);
  await status.focus();
  await expect(tooltip).toBeVisible();
  await status.press('Escape');
  await expect(tooltip).toHaveCount(0);
});
