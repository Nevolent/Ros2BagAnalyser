import { test, expect } from '@playwright/test';
import { apiFixture } from './api-fixture';
import { channels, duration } from '../src/data/fixtures/analysis';

const colors = ['rgb(0, 187, 127)', 'rgb(249, 156, 0)', 'rgb(141, 84, 255)'];

test('synthetic preview has dense bounded signals and stable initial readouts', async ({
  page,
}) => {
  expect(duration).toBe(75);
  for (const [name, signal] of Object.entries(channels)) {
    expect(signal.values, name).toHaveLength(6_000);
    expect(Math.max(...signal.values), name).toBeLessThan(signal.ticks[0]);
    expect(Math.min(...signal.values), name).toBeGreaterThan(signal.ticks.at(-1)!);
  }
  await page.goto('/?demo=1#/analysis');
  await expect(page.locator('[data-axis-value]')).toHaveText(['0.937']);
  await expect(page.locator('[data-axis-value]')).toHaveAttribute('data-axis-value', 'z');
  await page
    .locator('.analysis-timeline')
    .screenshot({ path: test.info().outputPath('analysis-z-axis.png') });
  const play = (await page
    .getByRole('button', { name: 'Play timeline', exact: true })
    .boundingBox())!;
  const mode = (await page.getByRole('button', { name: 'Choose sensor graph' }).boundingBox())!;
  expect(mode.x - play.x - play.width).toBeLessThanOrEqual(2);
  expect(mode.y + mode.height / 2).toBeCloseTo(play.y + play.height / 2, 1);
  const icon = (await page.locator('[data-timeline-play] svg').boundingBox())!;
  const titleCentre = await page.locator('[data-channel-label]').evaluate((el) => {
    const r = el.getBoundingClientRect();
    return r.y + (r.height - parseFloat(getComputedStyle(el).paddingBottom)) / 2;
  });
  expect(icon.y + icon.height / 2).toBeCloseTo(titleCentre, 1);
  for (const label of await page.locator('.timeline-axes label').all()) {
    const checkbox = (await label.locator('input').boundingBox())!;
    const text = (await label.locator('span').boundingBox())!;
    expect(
      Math.abs(checkbox.y + checkbox.height / 2 - text.y - text.height / 2),
    ).toBeLessThanOrEqual(1.5);
  }
  for (const axis of ['X', 'Y']) await page.getByRole('checkbox', { name: `${axis} axis` }).check();
  const paths = page.locator('[data-axis-trace] .timeline-line');
  await expect(paths).toHaveCount(3);
  for (const trace of await page.locator('[data-axis-trace]').all()) {
    await expect(trace).toHaveAttribute('opacity', '0.78');
  }
  expect(
    await paths.evaluateAll((elements) => elements.map((el) => getComputedStyle(el).stroke)),
  ).toEqual(colors);
  const plot = (await page.getByRole('slider').boundingBox())!;
  const grid = await page
    .locator('.timeline-grid line')
    .evaluateAll((elements) => elements.map((el) => Number(el.getAttribute('y1'))));
  for (const path of await paths.all()) {
    await expect(path).toHaveCSS('stroke-width', '1.2px');
    const bounds = (await path.boundingBox())!;
    expect(bounds.y).toBeGreaterThanOrEqual(plot.y + Math.min(...grid));
    expect(bounds.y + bounds.height).toBeLessThanOrEqual(plot.y + Math.max(...grid));
  }
  for (const [index, axis] of ['X', 'Y', 'Z'].entries()) {
    await expect(page.getByRole('checkbox', { name: `${axis} axis` })).toHaveCSS(
      'border-top-color',
      colors[index],
    );
    await expect(page.locator(`[data-axis-value=${axis.toLowerCase()}]`)).toHaveCSS(
      'color',
      colors[index],
    );
  }
  await page.screenshot({ path: test.info().outputPath('analysis-three-axes.png') });
  const measurement = page.locator('.timeline-measurement');
  const readout = (await measurement.boundingBox())!;
  expect(readout.y + readout.height).toBeLessThan(plot.y + Math.min(...grid));
  expect(Math.min(...grid)).toBe(33);
  const topLabel = (await page.locator('.timeline-grid text').first().boundingBox())!;
  expect(topLabel.x + topLabel.width).toBeLessThan(readout.x);
  expect(topLabel.y + topLabel.height).toBeLessThan(plot.y + Math.min(...grid));
  await expect(measurement.locator('strong').first()).toHaveCSS('font-size', '14px');
  const labelGap = await measurement
    .locator('.timeline-axis-reading')
    .first()
    .evaluate((el) => {
      const label = el.querySelector('span')!.getBoundingClientRect();
      const number = el.querySelector('strong')!.getBoundingClientRect();
      return label.x - number.right;
    });
  expect(labelGap).toBeCloseTo(3, 1);
  for (const input of await page
    .getByRole('group', { name: 'IMU axes' })
    .getByRole('checkbox')
    .all()) {
    await expect(input).toHaveClass('bag-checkbox');
    expect(await input.evaluate((el) => getComputedStyle(el, '::after').content)).not.toBe('none');
  }
});

test('ordinary graph hover shows no table and leaves seeking and playback unchanged', async ({
  page,
}) => {
  await apiFixture(page);
  const now = new Date('2026-10-09T10:00:00Z');
  await page.clock.install({ time: now });
  await page.clock.pauseAt(now);
  await page.goto('/#/analysis/42');
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  await expect(page.locator('[data-axis-trace]')).toHaveCount(1);
  await page.getByRole('checkbox', { name: 'X axis' }).check();
  await page.getByRole('button', { name: 'Play timeline', exact: true }).click();
  await page.clock.runFor(1100);
  const before = await plot.getAttribute('aria-valuenow');
  const box = (await plot.boundingBox())!;
  await page.mouse.move(box.x + box.width * 0.35, box.y + 80);
  const tooltip = page.locator('.chart-tooltip');
  await expect(tooltip).toHaveCount(0);
  await expect(plot).toHaveAttribute('aria-valuenow', before!);
  await page
    .locator('.analysis-timeline')
    .screenshot({ path: test.info().outputPath('analysis-hover.png') });
  await expect(page.getByRole('button', { name: 'Pause timeline', exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Pause timeline', exact: true }).click();
  await page.getByRole('checkbox', { name: 'Y axis' }).check();
  await page.mouse.move(box.x + box.width - 1, box.y + box.height - 12);
  await expect(tooltip).toHaveCount(0);
  await page.getByRole('heading', { name: 'Analysis', exact: true }).hover();
  await expect(tooltip).toHaveCount(0);
});

test('readout labels and values retain their positions across signs and coverage gaps', async ({
  page,
}) => {
  const api = await apiFixture(page);
  const values = [1, 98, -125.749, null, 0.001];
  api.imu.data.samples.forEach((row, i) => {
    for (let column = 1; column <= 6; column++) row[column] = values[i];
  });
  api.imu.state.artifact.series.forEach((series) => {
    series.minimum_value = -125.749;
    series.maximum_value = 98;
  });
  await page.goto('/#/analysis/42');
  const plot = page.getByRole('slider');
  await expect(page.locator('[data-axis-value=z]')).toHaveText('—');
  for (const axis of ['X', 'Y']) await page.getByRole('checkbox', { name: `${axis} axis` }).check();
  const positions = () =>
    page.locator('.timeline-axis-reading > *').evaluateAll((elements) =>
      elements.map((el) => {
        const rect = el.getBoundingClientRect();
        return { x: rect.x, width: rect.width };
      }),
    );
  const initial = await positions();
  const readings = page.locator('[data-axis-value]');
  for (const value of ['1.000', '-125.749', '—', '0.001']) {
    await plot.press('ArrowRight');
    await expect(readings).toHaveText([value, value, value]);
    expect(await positions()).toEqual(initial);
  }
  await page.getByRole('checkbox', { name: 'Z axis' }).uncheck();
  await expect(page.locator('[data-axis-trace]')).toHaveCount(2);
  await expect(readings).toHaveCount(2);
  await expect(readings).toHaveText(['0.001', '0.001']);
  await page.getByRole('checkbox', { name: 'Y axis' }).uncheck();
  await page.getByRole('checkbox', { name: 'X axis' }).uncheck();
  await expect(readings).toHaveCount(0);
  await page.getByRole('checkbox', { name: 'X axis' }).focus();
  await page.keyboard.press('Space');
  await expect(page.getByRole('checkbox', { name: 'X axis' })).toBeChecked();
  await expect(page.getByRole('button', { name: 'Play timeline', exact: true })).toBeVisible();
  await expect(plot).toHaveAttribute('aria-valuenow', '4');
});

test('the scale fits selected visible values and an empty selection keeps only the timeline grid', async ({
  page,
}) => {
  const api = await apiFixture(page);
  const columns = [
    [-120, -5, 75, null, -12],
    [-22, -34, -28, null, -30],
    [101, 101.5, 102, null, 101.25],
  ];
  columns.forEach((values, index) => {
    api.imu.data.samples.forEach((row, i) => {
      row[index + 4] = values[i];
    });
    const finite = values.filter((value): value is number => value !== null);
    api.imu.state.artifact.series[index + 3].minimum_value = Math.min(...finite);
    api.imu.state.artifact.series[index + 3].maximum_value = Math.max(...finite);
  });
  await page.goto('/#/analysis/42');
  await page.getByRole('button', { name: 'Choose sensor graph' }).click();
  await page.getByRole('menuitemradio', { name: 'Linear acceleration', exact: true }).click();
  const labels = page.locator('.timeline-grid text');
  const gridPositions = () =>
    page
      .locator('.timeline-grid line')
      .evaluateAll((lines) => lines.map((line) => line.getAttribute('y1')));
  const range = async () => {
    const ticks = (await labels.allTextContents()).map(Number);
    return { low: Math.min(...ticks), high: Math.max(...ticks) };
  };
  await expect(page.locator('[data-axis-value]')).toHaveCount(1);
  const originalGrid = await gridPositions();
  const z = await range();
  expect(z.low).toBeGreaterThanOrEqual(99);
  expect(z.low).toBeLessThan(101);
  expect(z.high).toBeGreaterThan(102);
  expect(z.high).toBeLessThanOrEqual(103);
  expect((z.high + z.low) / 2).toBe(101.5);
  expect(1 / (z.high - z.low)).toBeGreaterThan(0.85);
  await page.getByRole('checkbox', { name: 'Y axis' }).check();
  const yz = await range();
  expect(yz.low).toBeLessThan(-34);
  expect(yz.high).toBeGreaterThan(102);
  expect(136 / (yz.high - yz.low)).toBeGreaterThan(0.85);
  await expect(page.locator('[data-axis-value]')).toHaveCount(2);
  await page.getByRole('checkbox', { name: 'X axis' }).check();
  const xyz = await range();
  expect(xyz.low).toBeLessThan(-120);
  expect(xyz.high).toBeGreaterThan(102);
  expect(222 / (xyz.high - xyz.low)).toBeGreaterThan(0.85);
  await expect(page.locator('[data-axis-value]')).toHaveCount(3);
  for (const axis of ['X', 'Y'])
    await page.getByRole('checkbox', { name: `${axis} axis` }).uncheck();
  expect(await range()).toEqual(z);
  const plot = page.getByRole('slider');
  await plot.press('ArrowRight');
  for (let i = 0; i < 3; i++)
    await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  const zoomed = await range();
  expect(zoomed.high - zoomed.low).toBeLessThan(z.high - z.low);
  expect(zoomed.high).toBeLessThan(102);
  await page.getByRole('checkbox', { name: 'Z axis' }).uncheck();
  await expect(labels).toHaveCount(0);
  await expect(page.locator('.timeline-grid line')).toHaveCount(5);
  expect(await gridPositions()).toEqual(originalGrid);
  await expect(
    page.locator(
      '[data-axis-trace], [data-axis-value], [data-timeline-unit], .timeline-measurement',
    ),
  ).toHaveCount(0);
  await plot.hover();
  await expect(page.locator('.chart-tooltip')).toHaveCount(0);
  await plot.press('End');
  await expect(plot).toHaveAttribute('aria-valuenow', '6');
  await page
    .locator('.analysis-timeline')
    .screenshot({ path: test.info().outputPath('analysis-no-selection.png') });
  await page.getByRole('checkbox', { name: 'Y axis' }).check();
  const negative = await range();
  expect(negative.high).toBeLessThan(0);
  expect(negative.low).toBeLessThan(-30);
  expect(negative.high).toBeGreaterThan(-30);
  await expect(page.locator('[data-axis-value]')).toHaveText(['—']);
});

for (const value of [0, -0.003, 98]) {
  test(`constant ${value} has a finite padded scale`, async ({ page }) => {
    const api = await apiFixture(page);
    api.imu.data.samples.forEach((row) => {
      for (let column = 1; column <= 6; column++) row[column] = value;
    });
    api.imu.state.artifact.series.forEach((series) => {
      series.minimum_value = series.maximum_value = value;
      series.finite_sample_count = '5';
      series.non_finite_sample_count = '0';
    });
    await page.goto('/#/analysis/42');
    await expect(page.locator('[data-axis-trace]')).toHaveCount(1);
    const ticks = (await page.locator('.timeline-grid text').allTextContents()).map(Number);
    expect(ticks[2]).toBe(value);
    expect(ticks[0] - value).toBeCloseTo(value - ticks[4], 8);
    expect(ticks.every(Number.isFinite)).toBe(true);
    expect(Math.min(...ticks)).toBeLessThan(value);
    expect(Math.max(...ticks)).toBeGreaterThan(value);
    expect(await page.locator('[data-axis-trace] path').getAttribute('d')).not.toMatch(
      /NaN|Infinity/,
    );
  });
}

test('angular velocity fills the graph for one or several axes and after zoom', async ({
  page,
}) => {
  const api = await apiFixture(page);
  const values = [0, 0.1, 0.2, null, 0.05];
  api.imu.data.samples.forEach((row, index) => {
    row[3] = values[index];
  });
  api.imu.state.artifact.series[2].minimum_value = 0;
  api.imu.state.artifact.series[2].maximum_value = 0.2;
  await page.goto('/#/analysis/42');
  const assertFitted = async (low: number, high: number) => {
    await expect(page.locator('.timeline-grid text')).toHaveCount(5);
    const ticks = (await page.locator('.timeline-grid text').allTextContents()).map(Number);
    expect(ticks[0]).toBeGreaterThan(high);
    expect(ticks[4]).toBeLessThan(low);
    expect((high - low) / (ticks[0] - ticks[4])).toBeGreaterThan(0.85);
    const steps = ticks.slice(1).map((tick, index) => ticks[index] - tick);
    for (const step of steps) expect(step).toBeCloseTo(steps[0], 8);
  };
  await assertFitted(0, 0.2);
  const plot = (await page.getByRole('slider').boundingBox())!;
  expect(Number(await page.locator('.timeline-grid line').first().getAttribute('y1'))).toBe(33);
  expect(plot.height).toBeGreaterThanOrEqual(200);
  await page.getByRole('checkbox', { name: 'X axis' }).check();
  const xValues = api.imu.data.samples
    .map((row) => row[1])
    .filter((value) => value !== null) as number[];
  await assertFitted(Math.min(0, ...xValues), Math.max(0.2, ...xValues));
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  await assertFitted(Math.min(0, ...xValues.slice(0, 3)), Math.max(0.2, ...xValues.slice(0, 3)));
  await page.getByRole('checkbox', { name: 'X axis' }).uncheck();
  await assertFitted(0, 0.2);
});

for (const width of [390, 640]) {
  test(`selected readouts and scale labels stay spaced at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.goto('/?demo=1#/analysis');
    const picker = page.getByRole('button', { name: 'Choose sensor graph' });
    await picker.click();
    await page.getByRole('menuitemradio', { name: 'Linear acceleration', exact: true }).click();
    await expect(page.locator('[data-axis-value]')).toHaveText(['9.810']);
    const ticks = (await page.locator('.timeline-grid text').allTextContents()).map(Number);
    expect(Math.min(...ticks)).toBeGreaterThan(7);
    for (const axis of ['X', 'Y'])
      await page.getByRole('checkbox', { name: `${axis} axis` }).check();
    await expect(page.locator('[data-axis-value]')).toHaveCount(3);
    await page
      .locator('.analysis-timeline')
      .screenshot({ path: test.info().outputPath('linear-acceleration.png') });
    await picker.click();
    await page.getByRole('menuitemradio', { name: 'Encoders', exact: true }).click();
    await expect(page.locator('[data-encoder-value]')).toHaveCount(6);
    const readings = (await page.locator('.timeline-measurement').boundingBox())!;
    const label = (await page.locator('.timeline-grid text').first().boundingBox())!;
    const plot = (await page.getByRole('slider').boundingBox())!;
    const top = Number(await page.locator('.timeline-grid line').first().getAttribute('y1'));
    expect(label.x + label.width).toBeLessThan(readings.x);
    expect(readings.y + readings.height).toBeLessThan(plot.y + top);
    expect(label.y + label.height).toBeLessThan(plot.y + top);
    for (const control of await page.locator('.timeline-axes label').all()) {
      const checkbox = (await control.locator('input').boundingBox())!;
      const text = (await control.locator('span').boundingBox())!;
      expect(
        Math.abs(checkbox.y + checkbox.height / 2 - text.y - text.height / 2),
      ).toBeLessThanOrEqual(1.5);
    }
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(
      width,
    );
    await page.screenshot({ path: test.info().outputPath('encoders.png'), fullPage: true });
    for (const wheel of ['FL', 'FR', 'ML', 'MR', 'RL'])
      await page.getByRole('checkbox', { name: `${wheel} wheel` }).uncheck();
    await expect(page.locator('[data-encoder-value]')).toHaveCount(1);
    await expect(page.locator('[data-encoder-value]')).toHaveAttribute(
      'data-encoder-value',
      'encoder.RR',
    );
    await expect(page.locator('[data-encoder-value]')).toHaveCSS('color', 'rgb(229, 211, 79)');
    const singleReading = (await page.locator('.timeline-measurement').boundingBox())!;
    expect(plot.y + top - 6 - singleReading.y - singleReading.height).toBeCloseTo(2.5, 1);
    await expect(page.locator('[data-encoder-trace]')).toHaveAttribute('opacity', '1');
    await page.getByRole('checkbox', { name: 'RR wheel' }).uncheck();
    await expect(page.locator('.timeline-grid text, .timeline-axis-reading')).toHaveCount(0);
    await expect(page.locator('.timeline-grid line')).toHaveCount(5);
    await page
      .locator('.analysis-timeline')
      .screenshot({ path: test.info().outputPath('no-selection.png') });
  });
}
