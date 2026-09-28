import { test, expect } from '@playwright/test';
import { apiFixture } from './api-fixture';

test('dense traces stay painted while playback and scrubbing update the cursor', async ({
  page,
}) => {
  const api = await apiFixture(page);
  const count = 60_001;
  api.recording.duration_ns = '60000000000';
  api.imu.data.samples = Array.from({ length: count }, (_, i) => [
    String(i * 1000000),
    ...Array.from({ length: 6 }, (_, axis) => Math.sin(i * (axis + 1))),
  ]);
  const metadata = api.imu.state.artifact;
  metadata.coverage_start_ns = '0';
  metadata.coverage_end_ns = '60000000000';
  metadata.delivered_sample_count = String(count);
  for (const series of metadata.series) {
    const values = api.imu.data.samples.map((row) => row[series.column_index] as number);
    series.minimum_value = values.reduce((a, b) => Math.min(a, b), Infinity);
    series.maximum_value = values.reduce((a, b) => Math.max(a, b), -Infinity);
    series.finite_sample_count = String(count);
    series.non_finite_sample_count = '0';
  }
  await page.goto('/#/analysis/42');
  await expect(page.locator('[data-channel-label]')).toHaveText('angular_velocity.z');

  // DOM memoization alone does not prevent expensive browser rasterization.
  // Inspect the actual compositor layer rather than relying on machine-specific FPS.
  const cdp = await page.context().newCDPSession(page);
  let layers: { backendNodeId?: number; paintCount: number; drawsContent: boolean }[] = [];
  cdp.on('LayerTree.layerTreeDidChange', (event) => {
    layers = event.layers ?? [];
  });
  await cdp.send('LayerTree.enable');
  const { root } = await cdp.send('DOM.getDocument');
  const { nodeId } = await cdp.send('DOM.querySelector', {
    nodeId: root.nodeId,
    selector: 'svg:has(.timeline-line)',
  });
  const { node } = await cdp.send('DOM.describeNode', { nodeId });
  const layer = () => layers.find((entry) => entry.backendNodeId === node.backendNodeId);
  await expect.poll(() => layer()?.drawsContent).toBe(true);
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  const box = (await plot.boundingBox())!;
  for (const channel of metadata.series.map((series) => series.component)) {
    await page.getByRole('button', { name: 'Choose sensor graph' }).click();
    await page.getByRole('menuitemradio', { name: channel, exact: true }).click();
    const cursor = page.locator('.timeline-cursor');
    const initialCursor = await cursor.getAttribute('style');
    await page.getByRole('button', { name: 'Play timeline', exact: true }).click();
    // Flush the new channel/control state before measuring steady playback.
    await page.screenshot();
    const playbackPaints = layer()!.paintCount;
    const initialTime = Number(await plot.getAttribute('aria-valuenow'));
    await expect
      .poll(async () => Number(await plot.getAttribute('aria-valuenow')))
      .toBeGreaterThan(initialTime + 0.3);
    await expect(cursor).not.toHaveAttribute('style', initialCursor!);
    await page.screenshot();
    expect(layer()!.paintCount, `${channel} playback must reuse the trace`).toBe(playbackPaints);
    await page.getByRole('button', { name: 'Pause timeline', exact: true }).click();
    await page.mouse.move(box.x + box.width * 0.2, box.y + 50);
    await page.mouse.down();
    // Focus and entering the drag state may paint once; pointer moves must reuse it.
    await page.screenshot();
    const scrubPaints = layer()!.paintCount;
    await page.mouse.move(box.x + box.width * 0.8, box.y + 50, { steps: 12 });
    expect(Number(await plot.getAttribute('aria-valuenow'))).toBeCloseTo(48, 1);
    await page.screenshot();
    expect(layer()!.paintCount, `${channel} scrubbing must reuse the trace`).toBe(scrubPaints);
    await page.mouse.up();
    await plot.press('Home');
  }
  await cdp.detach();
});
