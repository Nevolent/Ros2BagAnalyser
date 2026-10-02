import { test, expect } from '@playwright/test';

const unixStart = 1771027200;
const duration = 754.56;

test('scrubbing follows the pointer before the next seek frame', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-10-01T10:00:00Z') });
  await page.clock.pauseAt(new Date('2026-10-01T10:00:00Z'));
  await page.goto('/?demo=1#/analysis');
  await page.clock.runFor(100);
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  const box = (await plot.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.2, box.y + 100);
  await page.mouse.down();
  const pointerX = box.x + box.width * 0.8;
  await page.mouse.move(pointerX, box.y + 100);
  const cursor = (await page.locator('.timeline-cursor').boundingBox())!;
  expect(Math.abs(cursor.x - pointerX)).toBeLessThan(1);
  await page.clock.runFor(17);
  expect(Number(await page.locator('[data-timeline-time]').textContent())).toBeCloseTo(
    unixStart + duration * 0.8,
    2,
  );
  await page.mouse.up();
});

test('right-hand value and unit lift near the playhead and settle back above the grid line', async ({
  page,
}) => {
  await page.goto('/?demo=1#/analysis');
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  const box = (await plot.boundingBox())!;
  const scale = page.locator('.timeline-grid text').first();
  const measurement = page.locator('.timeline-measurement');
  const center = () => plot.click({ position: { x: box.width / 2, y: 100 } });
  await center();
  await expect(measurement).toHaveCSS('transform', 'none');
  const restingScale = (await scale.boundingBox())!;
  const restingValue = (await measurement.boundingBox())!;
  await page
    .locator('.analysis-timeline')
    .screenshot({ path: test.info().outputPath('labels-resting.png') });
  await plot.press('End');
  await expect
    .poll(async () => (await measurement.boundingBox())!.y)
    .toBeCloseTo(restingValue.y - 4, 1);
  expect(await scale.boundingBox()).toEqual(restingScale);
  await page
    .locator('.analysis-timeline')
    .screenshot({ path: test.info().outputPath('labels-near-playhead.png') });
  await center();
  await expect
    .poll(async () => (await measurement.boundingBox())!.y)
    .toBeCloseTo(restingValue.y, 1);
  expect(await scale.boundingBox()).toEqual(restingScale);
});

for (const viewport of [
  { width: 1440, height: 900 },
  { width: 1920, height: 600 },
  { width: 640, height: 844 },
  { width: 390, height: 844 },
]) {
  test(`camera ratios survive details resizing and collapse at ${viewport.width}×${viewport.height}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport);
    await page.goto('/?demo=1#/analysis');
    const front = page.locator('.analysis-camera-front');
    const top = page.locator('.analysis-camera-top');
    async function checkRatios() {
      await expect
        .poll(async () => {
          const box = (await front.boundingBox())!;
          return box.width / box.height;
        })
        .toBeCloseTo(16 / 9, 2);
      await expect
        .poll(async () => {
          const box = (await top.boundingBox())!;
          return box.width / box.height;
        })
        .toBeCloseTo(4 / 3, 2);
    }
    await checkRatios();
    if (viewport.width > 600) {
      const splitter = page.getByRole('separator', { name: 'Resize recording details' });
      const rows = page.locator('.recording-info > div,.recording-assets li');
      const before = await rows.evaluateAll((items) =>
        items.map((el) => el.getBoundingClientRect().height),
      );
      const box = (await splitter.boundingBox())!;
      await page.mouse.move(box.x + box.width / 2, box.y + 50);
      await page.mouse.down();
      await page.mouse.move(viewport.width - 25, box.y + 50);
      await page.mouse.up();
      await expect(splitter).toHaveAttribute('aria-valuenow', '280');
      expect(
        await rows.evaluateAll((items) => items.map((el) => el.getBoundingClientRect().height)),
      ).toEqual(before);
      await checkRatios();
      await splitter.press('ArrowLeft');
      await checkRatios();
    }
    await page.getByRole('button', { name: 'Collapse recording details' }).click();
    await checkRatios();
    await page.getByRole('button', { name: 'Expand recording details' }).click();
    await checkRatios();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <= innerWidth &&
          document.documentElement.scrollHeight <= innerHeight,
      ),
    ).toBe(true);
  });
}

test('Shift drag previews Unix boundaries and zooms in both directions without seeking', async ({
  page,
}) => {
  await page.goto('/?demo=1#/analysis');
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  const reset = page.getByRole('button', { name: 'Reset zoom', exact: true });
  await expect(reset).toBeDisabled();
  for (const [from, to] of [
    [0.2, 0.7],
    [0.7, 0.2],
  ]) {
    const box = (await plot.boundingBox())!;
    await page.keyboard.down('Shift');
    await page.mouse.move(box.x + box.width * from, box.y + 100);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * to, box.y + 100, { steps: 5 });
    const start = Number(await page.locator('[data-selection-start]').textContent());
    const end = Number(await page.locator('[data-selection-end]').textContent());
    expect(start).toBeCloseTo(unixStart + duration * 0.2, 0);
    expect(end).toBeCloseTo(unixStart + duration * 0.7, 0);
    await expect(plot).toHaveAttribute('aria-valuenow', '0');
    if (from < to)
      await page.screenshot({ path: test.info().outputPath('analysis-shift-selection.png') });
    await page.mouse.up();
    await page.keyboard.up('Shift');
    await expect(page.locator('.timeline-selection')).toHaveCount(0);
    await expect(reset).toBeEnabled();
    expect(Number(await page.locator('[data-timeline-end]').textContent())).toBeCloseTo(end, 2);
    await expect(page.locator('[data-timeline-time]')).toHaveText('1771027200.000');
    await plot.press('Escape');
    // Seeking within the selected view uses its new time range.
    await plot.click({ position: { x: box.width * 0.5, y: 100 } });
    expect(Number(await plot.getAttribute('aria-valuenow'))).toBeCloseTo(duration * 0.45, 0);
    await reset.click();
    await expect(reset).toBeDisabled();
    await plot.press('Home');
  }
});

test('Shift selection cancels cleanly and ignores tiny drags', async ({ page }) => {
  await page.goto('/?demo=1#/analysis');
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  const box = (await plot.boundingBox())!;
  const reset = page.getByRole('button', { name: 'Reset zoom', exact: true });
  for (const cancel of ['Escape', 'pointercancel', 'tiny']) {
    await page.keyboard.down('Shift');
    await page.mouse.move(box.x + 40, box.y + 100);
    await page.mouse.down();
    await page.mouse.move(box.x + (cancel === 'tiny' ? 43 : box.width / 2), box.y + 100);
    if (cancel === 'Escape') await page.keyboard.press('Escape');
    if (cancel === 'pointercancel') await plot.dispatchEvent('pointercancel');
    await page.mouse.up();
    await page.keyboard.up('Shift');
    await expect(reset).toBeDisabled();
    await expect(page.locator('.timeline-selection')).toHaveCount(0);
    await expect(plot).toHaveAttribute('aria-valuenow', '0');
  }
  await plot.press('ArrowRight');
  await expect(page.locator('[data-timeline-time]')).toHaveText('1771027201.000');
});

test('all six channels update units and keep the clock, with keyboard access across groups', async ({
  page,
}) => {
  await page.goto('/?demo=1#/analysis');
  const trigger = page.getByRole('button', { name: 'Choose sensor graph' });
  await trigger.click();
  await expect(page.getByRole('menuitemradio')).toHaveCount(6);
  await page.getByRole('menuitemradio', { name: 'linear_acceleration.z', exact: true }).click();
  await expect(page.locator('[data-timeline-unit]')).toHaveText('m/s²');
  await expect(page.locator('[data-timeline-time]')).toHaveText('1771027200.000');
  expect(Number(await page.locator('[data-timeline-value]').textContent())).toBeGreaterThan(9);
  await trigger.press('ArrowDown');
  await page.keyboard.press('ArrowLeft');
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-channel-label]')).toHaveText('angular_velocity.z');
  await expect(page.locator('[data-timeline-unit]')).toHaveText('rad/s');
});

test('zoom buttons stay anchored inside a Shift-selected range when playback is outside it', async ({
  page,
}) => {
  await page.goto('/?demo=1#/analysis');
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  const box = (await plot.boundingBox())!;
  await page.keyboard.down('Shift');
  await page.mouse.move(box.x + box.width * 0.3, box.y + 100);
  await page.mouse.down();
  await page.mouse.move(box.x + box.width * 0.7, box.y + 100);
  await page.mouse.up();
  await page.keyboard.up('Shift');
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  expect(Number(await page.locator('[data-timeline-end]').textContent())).toBeCloseTo(
    unixStart + duration * 0.6,
    0,
  );
  await plot.click({ position: { x: box.width * 0.5, y: 100 } });
  expect(Number(await plot.getAttribute('aria-valuenow'))).toBeCloseTo(duration * 0.5, 0);
});

test('graph geometry updates before paint throughout panel dragging and collapse', async ({
  page,
}) => {
  await page.goto('/?demo=1#/analysis');
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  await plot.press('ArrowRight');
  await page.evaluate(() => {
    const plot = document.querySelector<HTMLElement>('[data-timeline-plot]')!;
    const svg = plot.querySelector<SVGSVGElement>('[data-timeline-svg]')!;
    const trace = plot.querySelector<SVGSVGElement>('[data-timeline-trace-svg]')!;
    const snapshots: {
      widthError: number;
      heightError: number;
      cursorError: number;
      cameraError: number;
    }[] = [];
    const observer = new ResizeObserver(() => {
      // Observe the geometry that will actually be painted after all resize callbacks.
      queueMicrotask(() => {
        const box = plot.getBoundingClientRect();
        const viewBox = svg.viewBox.baseVal;
        const cameras = document
          .querySelector<HTMLElement>('.analysis-cameras')!
          .getBoundingClientRect();
        const workspace = document
          .querySelector<HTMLElement>('.analysis-workspace')!
          .getBoundingClientRect();
        const expectedCameraHeight = Math.min(
          ((cameras.width - 8) * 9) / 28,
          workspace.height - 228,
        );
        const cursor = plot.querySelector<HTMLElement>('.timeline-cursor')!;
        const cursorX = cursor.getBoundingClientRect().left - box.left;
        snapshots.push({
          widthError: Math.max(
            Math.abs(viewBox.width - box.width),
            Math.abs(trace.viewBox.baseVal.width - box.width),
          ),
          heightError: Math.max(
            Math.abs(viewBox.height - box.height),
            Math.abs(trace.viewBox.baseVal.height - box.height),
          ),
          cursorError: Math.abs(cursorX - Math.round(box.width / 754.56)),
          cameraError: Math.abs(cameras.height - expectedCameraHeight),
        });
      });
    });
    observer.observe(plot);
    (
      window as typeof window & { resizeAudit?: { snapshots: typeof snapshots; stop(): void } }
    ).resizeAudit = { snapshots, stop: () => observer.disconnect() };
  });
  const splitter = page.getByRole('separator', { name: 'Resize recording details' });
  const box = (await splitter.boundingBox())!;
  await page.mouse.move(box.x + box.width / 2, box.y + 80);
  await page.mouse.down();
  await page.mouse.move(box.x - 250, box.y + 80, { steps: 15 });
  await page.mouse.move(box.x, box.y + 80, { steps: 15 });
  await page.mouse.up();
  for (let i = 0; i < 3; i++) {
    await page.getByRole('button', { name: 'Collapse recording details' }).click();
    await page.getByRole('button', { name: 'Expand recording details' }).click();
  }
  const snapshots = await page.evaluate(() => {
    const audit = (
      window as typeof window & {
        resizeAudit: {
          snapshots: {
            widthError: number;
            heightError: number;
            cursorError: number;
            cameraError: number;
          }[];
          stop(): void;
        };
      }
    ).resizeAudit;
    audit.stop();
    return audit.snapshots;
  });
  expect(snapshots.length).toBeGreaterThan(10);
  expect(snapshots.filter((sample) => Object.values(sample).some((error) => error >= 1))).toEqual(
    [],
  );
  await expect(plot).toHaveAttribute('aria-valuenow', '1');
});

test('Analysis owns playback shortcuts without plot focus and yields to interactive widgets', async ({
  page,
}) => {
  await page.goto('/?demo=1#/analysis');
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  await page.keyboard.press('ArrowRight');
  await expect(plot).toHaveAttribute('aria-valuenow', '1');
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await page.keyboard.press('ArrowRight');
  await expect(plot).toHaveAttribute('aria-valuenow', '2');
  await page.keyboard.press('Space');
  await expect(page.getByRole('button', { name: 'Pause timeline', exact: true })).toBeVisible();
  await page.keyboard.press('Space');
  await expect(page.getByRole('button', { name: 'Play timeline', exact: true })).toBeVisible();
  await plot.press('Home');
  await page.getByRole('button', { name: 'Play timeline', exact: true }).focus();
  await page.keyboard.press('Space');
  await expect(page.getByRole('button', { name: 'Pause timeline', exact: true })).toBeVisible();
  await page.keyboard.press('Space');
  await plot.press('Home');
  await page.getByRole('button', { name: 'Choose sensor graph' }).click();
  await page.keyboard.press('ArrowRight');
  await expect(plot).toHaveAttribute('aria-valuenow', '0');
  await page.keyboard.press('Escape');
  const splitter = page.getByRole('separator', { name: 'Resize recording details' });
  await splitter.press('ArrowLeft');
  await expect(plot).toHaveAttribute('aria-valuenow', '0');
  await page.keyboard.press('Control+k');
  const search = page.getByRole('combobox');
  await search.fill('record');
  await page.keyboard.press('Space');
  await expect(search).toHaveValue('record ');
  await page.keyboard.press('ArrowRight');
  await expect(plot).toHaveAttribute('aria-valuenow', '0');
  await page.keyboard.press('Escape');
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await expect(plot).toHaveCount(0);
  expect(
    await page.evaluate(() => {
      const event = new KeyboardEvent('keydown', { key: ' ', bubbles: true, cancelable: true });
      document.dispatchEvent(event);
      return event.defaultPrevented;
    }),
  ).toBe(false);
});

test('playhead advances fractionally every frame between readout commits', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-30T10:00:00Z') });
  await page.clock.pauseAt(new Date('2026-09-30T10:00:00Z'));
  await page.goto('/?demo=1#/analysis');
  await page.clock.runFor(100);
  await page.keyboard.press('Space');
  const positions: number[] = [];
  for (let i = 0; i < 8; i++) {
    await page.clock.runFor(17);
    positions.push(
      await page.locator('.timeline-cursor').evaluate((el) => el.getBoundingClientRect().x),
    );
  }
  for (let i = 1; i < positions.length; i++) {
    expect(positions[i]).toBeGreaterThan(positions[i - 1]);
    expect(positions[i] - positions[i - 1]).toBeLessThan(0.1);
  }
  await page.keyboard.press('Space');
  const paused = await page.locator('.timeline-cursor').getAttribute('style');
  await page.clock.runFor(100);
  await expect(page.locator('.timeline-cursor')).toHaveAttribute('style', paused!);
});
