import { test, expect } from '@playwright/test';
import { PNG } from 'pngjs';
import { apiFixture } from './api-fixture';

for (const zoom of [1, 1.25, 2]) {
  test(`toolbar and graph controls share their vertical centres at ${zoom * 100}% scale`, async ({
    page,
  }) => {
    await page.setViewportSize({
      width: zoom === 1 ? 2560 : Math.round(1440 * zoom),
      height: zoom === 1 ? 1440 : Math.round(1000 * zoom),
    });
    await page.goto('/?demo=1');
    await page.evaluate((zoom) => {
      document.documentElement.style.zoom = String(zoom);
    }, zoom);
    await page.locator('.bag-table tbody .bag-checkbox').first().check();
    const centres = await page.locator('.recordings-toolbar').evaluate((element) => {
      const selectors = [
        '.bag-search-field input',
        '.bag-filter button > span',
        '.prepare-selected > span',
      ];
      return selectors.flatMap((selector) =>
        [...element.querySelectorAll(selector)].map((el) => {
          const r = el.getBoundingClientRect();
          return r.y + r.height / 2;
        }),
      );
    });
    expect(Math.max(...centres) - Math.min(...centres)).toBeLessThan(0.1);
    const pills = await page
      .locator('.recordings-toolbar .bag-filter, .recordings-toolbar .prepare-selected')
      .all();
    for (let i = 1; i < pills.length; i++) {
      const before = (await pills[i - 1].boundingBox())!,
        next = (await pills[i].boundingBox())!;
      expect((next.x - before.x - before.width) / zoom).toBeCloseTo(4, 1);
    }
    const toggle = (await page.locator('.folder-toggle svg path').boundingBox())!;
    const search = (await page.locator('.folder-search-field').boundingBox())!;
    expect(toggle.x + toggle.width).toBeCloseTo(search.x + search.width, 1);
    await page.screenshot({ path: test.info().outputPath('recordings.png') });
    await page.getByRole('link', { name: 'Analysis', exact: true }).click();
    for (const graph of ['Angular velocity', 'Linear acceleration', 'Encoders']) {
      await page.getByRole('button', { name: 'Choose sensor graph' }).click();
      await page.getByRole('menuitemradio', { name: graph, exact: true }).click();
      const centres = await page.locator('.analysis-graph-heading').evaluate((element) => {
        const selectors = [
          '[data-timeline-play] svg > *',
          '[data-channel-label]',
          '.timeline-axes input',
          '.timeline-axes label > span',
        ];
        const scale = Number(getComputedStyle(document.documentElement).zoom);
        return selectors.flatMap((selector) =>
          [...element.querySelectorAll(selector)].map((el) => {
            const r = el.getBoundingClientRect();
            // The title's clip includes descenders; its capitals supply the alignment box.
            const padding = parseFloat(getComputedStyle(el).paddingBottom) * scale;
            return r.y + (r.height - padding) / 2;
          }),
        );
      });
      expect(Math.max(...centres) - Math.min(...centres)).toBeLessThan(0.1);
      const labels = await page.locator('.timeline-axes label').all();
      for (let i = 1; i < labels.length; i++) {
        const before = (await labels[i - 1].boundingBox())!,
          next = (await labels[i].boundingBox())!;
        expect((next.x - before.x - before.width) / zoom).toBeCloseTo(10, 1);
      }
      const pitches = await page
        .locator('.timeline-axes label > span')
        .evaluateAll((elements) => elements.map((el) => el.getBoundingClientRect().x));
      for (let i = 2; i < pitches.length; i++)
        expect(pitches[i] - pitches[i - 1]).toBeCloseTo(pitches[1] - pitches[0], 1);
      for (const checkbox of await page.locator('.timeline-axes input:not(:disabled)').all())
        await checkbox.check();
      const baselines = await page
        .locator('.timeline-measurement strong, .timeline-reading-label, [data-timeline-unit]')
        .evaluateAll((elements) =>
          elements.map((el) => {
            const probe = document.createElement('i');
            probe.style.cssText =
              'display:inline-block;width:0;height:0;padding:0;margin:0;border:0';
            el.append(probe);
            const baseline = probe.getBoundingClientRect().y;
            probe.remove();
            return baseline;
          }),
        );
      expect(Math.max(...baselines) - Math.min(...baselines)).toBeLessThan(0.1);
      const values = (await page.locator('.timeline-measurement').boundingBox())!;
      const cursor = (await page.locator('.timeline-cursor').boundingBox())!;
      expect((cursor.y - values.y - values.height) / zoom - 6).toBeCloseTo(2.5, 1);
      await page
        .locator('.analysis-timeline')
        .screenshot({ path: test.info().outputPath(`${graph}.png`) });
    }
  });
}

test('Thumbnail is first and resets on reload while Compact survives route navigation', async ({
  page,
}) => {
  await apiFixture(page);
  await page.goto('/');
  const choices = page.getByRole('group', { name: 'Recording view' }).getByRole('button');
  await expect(choices).toHaveText(['Thumbnail', 'Compact']);
  await expect(choices.first()).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.bag-table')).toHaveClass(/bag-table-thumbnails/);
  await choices.last().click();
  await page.getByRole('link', { name: 'Analysis', exact: true }).click();
  await page.getByRole('link', { name: 'Recordings', exact: true }).click();
  await expect(choices.last()).toHaveAttribute('aria-pressed', 'true');
  await page.reload();
  await expect(choices.first()).toHaveAttribute('aria-pressed', 'true');
  await expect(page.locator('.bag-table')).toHaveClass(/bag-table-thumbnails/);
});

test('mixed signs and digit counts keep compact equal readout pitch and a 2.5px baseline gap', async ({
  page,
}) => {
  const api = await apiFixture(page);
  const examples = [1, -125.749, 98, 0.001, -8];
  api.imu.data.samples.forEach((row, i) => {
    for (let column = 1; column <= 6; column++)
      row[column] = examples[(i + column) % examples.length];
  });
  api.imu.state.artifact.series.forEach((series, i) => {
    const values = api.imu.data.samples.map((row) => row[i + 1] as number);
    series.finite_sample_count = '5';
    series.non_finite_sample_count = '0';
    series.minimum_value = Math.min(...values);
    series.maximum_value = Math.max(...values);
  });
  await page.goto('/#/analysis/42');
  for (const axis of ['X', 'Y']) await page.getByRole('checkbox', { name: `${axis} axis` }).check();
  const labels = () =>
    page.locator('.timeline-reading-label').evaluateAll((elements) =>
      elements.map((el) => {
        const r = el.getBoundingClientRect();
        return { x: r.x, y: r.y, width: r.width };
      }),
    );
  const initial = await labels();
  expect(initial[1].x - initial[0].x).toBeCloseTo(initial[2].x - initial[1].x, 1);
  const readings = await page.locator('.timeline-axis-reading').all();
  for (let i = 1; i < readings.length; i++) {
    const before = (await readings[i - 1].boundingBox())!,
      next = (await readings[i].boundingBox())!;
    expect(next.x - before.x - before.width).toBeCloseTo(2, 1);
  }
  const last = (await readings.at(-1)!.boundingBox())!;
  const unit = (await page.locator('[data-timeline-unit]').boundingBox())!;
  expect(unit.x - last.x - last.width).toBeCloseTo(10, 1);
  for (let i = 0; i < 5; i++) {
    await page.getByRole('slider').press('ArrowRight');
    expect(await labels()).toEqual(initial);
  }
  const measurement = (await page.locator('.timeline-measurement').boundingBox())!;
  const cursor = (await page.locator('.timeline-cursor').boundingBox())!;
  const timeline = (await page.locator('.analysis-timeline').boundingBox())!;
  expect(cursor.y - 6 - measurement.y - measurement.height).toBeCloseTo(2.5, 1);
  const png = PNG.sync.read(
    await page
      .locator('.analysis-timeline')
      .screenshot({ path: test.info().outputPath('readout-ink-gap.png') }),
  );
  let lastColouredRow = -1;
  for (
    let y = Math.floor(measurement.y - timeline.y);
    y < Math.ceil(measurement.y + measurement.height - timeline.y);
    y++
  ) {
    for (
      let x = Math.floor(measurement.x - timeline.x);
      x < Math.ceil(measurement.x + measurement.width - timeline.x);
      x++
    ) {
      const offset = (y * png.width + x) * 4;
      const rgb = [...png.data.subarray(offset, offset + 3)];
      if (Math.max(...rgb) > 90 && Math.max(...rgb) - Math.min(...rgb) > 55) lastColouredRow = y;
    }
  }
  expect(lastColouredRow).toBeGreaterThan(0);
  expect(Math.round(cursor.y - timeline.y - 6) - lastColouredRow - 1).toBe(2);
});

test('archive icon matches rail weight and rotates counterclockwise, with a reduced-motion state', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  const button = page.locator('.sidebar-settings-trigger');
  const icon = button.locator('svg');
  await expect(icon).toHaveCSS('width', '16px');
  await expect(icon).toHaveCSS('height', '16px');
  await expect(icon).toHaveAttribute('stroke-width', '2');
  await expect(icon).toHaveAttribute('stroke-linecap', 'round');
  await button.click();
  await expect(button).toHaveAccessibleName('Scanning archive');
  const sine = await icon.evaluate((el) => {
    const animation = el.getAnimations()[0];
    animation.pause();
    animation.currentTime = 250;
    return new DOMMatrix(getComputedStyle(el).transform).b;
  });
  expect(sine).toBeCloseTo(-1, 2);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await expect(icon).toHaveCSS('animation-name', 'none');
  await expect(button).toHaveAttribute('aria-busy', 'true');
});
