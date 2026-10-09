import { expect, test } from '@playwright/test';
import { apiFixture } from './api-fixture';

function encoderFixture() {
  const components = [
    'encoder.FL',
    'encoder.FR',
    'encoder.ML',
    'encoder.MR',
    'encoder.RL',
    'encoder.RR',
  ];
  const values = [
    [1, 2, 3, 4, 5, 6],
    [8, 18, 8, 18, 8, 18],
    [19, 5, 19, 5, 19, 5],
    [null, 9, 10, 11, 12, 13],
    [14, 15, 16, 17, 18, 19],
  ];
  const artifact = {
    data_url: '/api/recordings/42/encoder-series/data/5',
    size_bytes: '1024',
    coverage_start_ns: '1000000000',
    coverage_end_ns: '4000000000',
    delivered_sample_count: '5',
    default_series_id: 'wheel_fl',
    series: components.map((component, index) => {
      const finite = values
        .map((row) => row[index])
        .filter((value): value is number => value !== null);
      return {
        id: `wheel_${component.slice(8).toLowerCase()}`,
        component,
        display_label: component,
        units: 'RPM',
        column_index: index + 1,
        finite_sample_count: String(finite.length),
        non_finite_sample_count: String(5 - finite.length),
        minimum_value: Math.min(...finite),
        maximum_value: Math.max(...finite),
        available: true,
      };
    }),
  };
  return {
    state: { state: 'ready', artifact },
    data: {
      schema_version: 2,
      samples: ['1000000000', '2000000000', '2000000000', '3000000000', '4000000000'].map(
        (time, index) => [time, ...values[index]],
      ),
    },
  };
}

async function setup(page: Parameters<typeof apiFixture>[0]) {
  const api = await apiFixture(page);
  const encoder = encoderFixture();
  api.recording.outputs.push({
    kind: 'encoder_series',
    state: 'ready',
    diagnostic: null,
    artifact: {
      id: 5,
      url: encoder.state.artifact.data_url,
      mime_type: 'application/json',
      size_bytes: '1024',
      coverage_start_ns: '1000000000',
      coverage_end_ns: '4000000000',
    },
  });
  api.override = async (route, path) => {
    if (path === '/api/recordings/42/encoder-series') {
      await route.fulfill({ json: encoder.state });
      return true;
    }
    if (path === '/api/recordings/42/encoder-series/data/5') {
      await route.fulfill({ json: encoder.data });
      return true;
    }
    return false;
  };
  return { api, encoder };
}

test('six wheel traces use recorded values, last duplicates, per-wheel gaps and measured coverage', async ({
  page,
}) => {
  await setup(page);
  await page.goto('/#/analysis/42');
  await page.getByRole('button', { name: 'Choose sensor graph' }).click();
  await page.getByRole('menuitemradio', { name: 'Encoders', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Encoder timeline' })).toBeVisible();
  await expect(page.locator('[data-encoder-trace]')).toHaveCount(6);
  await expect(page.getByRole('group', { name: 'Wheel encoder readings' })).toBeVisible();
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  const reading = (wheel: string) => page.locator(`[data-encoder-value="encoder.${wheel}"]`);
  await plot.press('Home');
  await expect(reading('FL')).toHaveText('—');
  await plot.press('ArrowRight');
  await expect(reading('FL')).toHaveText('1.000');
  await expect(reading('RR')).toHaveText('6.000');
  await plot.press('ArrowRight');
  await expect(reading('FL')).toHaveText('19.000');
  await expect(reading('FR')).toHaveText('5.000');
  await page.screenshot({ path: 'artifacts/encoder-desktop.png', fullPage: true });
  await plot.press('ArrowRight');
  await expect(reading('FL')).toHaveText('—');
  await expect(reading('FR')).toHaveText('9.000');
  await plot.press('End');
  for (const wheel of ['FL', 'FR', 'ML', 'MR', 'RL', 'RR'])
    await expect(reading(wheel)).toHaveText('—');
  for (const wheel of ['FR', 'ML', 'MR', 'RL', 'RR'])
    await page.getByRole('checkbox', { name: `${wheel} wheel` }).uncheck();
  await expect(page.locator('[data-encoder-trace]')).toHaveCount(1);
  await expect(page.locator('[data-encoder-value]')).toHaveCount(1);
  await expect(page.locator('[data-encoder-trace]')).toHaveAttribute(
    'data-encoder-trace',
    'encoder.FL',
  );
  await expect(page.locator('[data-timeline-unit]')).toHaveText('RPM');
  await plot.press('Home');
  await plot.press('ArrowRight');
  await expect(reading('FL')).toHaveText('1.000');
});

test('encoder artifact mismatch keeps the prepared IMU graph usable', async ({ page }) => {
  const { encoder } = await setup(page);
  encoder.state.artifact.data_url = '/api/recordings/42/encoder-series/data/99';
  await page.goto('/#/analysis/42');
  await expect(page.getByRole('region', { name: 'IMU timeline' })).toBeVisible();
  await expect(page.getByRole('region', { name: 'Recording errors' })).toContainText(
    'Encoder artifact identity changed',
  );
  await page.getByRole('button', { name: 'Choose sensor graph' }).click();
  await expect(page.getByRole('menuitemradio', { name: 'Encoders', exact: true })).toBeDisabled();
});

test('six wheels remain usable on a small viewport with reduced motion and without IMU', async ({
  page,
}) => {
  const { api } = await setup(page);
  api.recording.outputs = api.recording.outputs.filter(
    (output) => output.kind === 'encoder_series',
  );
  await page.setViewportSize({ width: 390, height: 844 });
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await page.goto('/#/analysis/42');
  await page.getByRole('button', { name: 'Choose sensor graph' }).click();
  await page.getByRole('menuitemradio', { name: 'Encoders', exact: true }).click();
  await expect(page.locator('[data-encoder-trace]')).toHaveCount(6);
  const legend = page.getByRole('group', { name: 'Wheel encoder readings' });
  await expect(legend).toBeVisible();
  const bounds = await legend.boundingBox();
  expect(bounds!.x).toBeGreaterThanOrEqual(0);
  expect(bounds!.x + bounds!.width).toBeLessThanOrEqual(390);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390);
  const scale = (await page.locator('.timeline-grid text').first().boundingBox())!;
  expect(scale.y).toBeGreaterThanOrEqual(bounds!.y + bounds!.height);
  await page.screenshot({ path: 'artifacts/encoder-mobile.png', fullPage: true });
});

test('encoder checkboxes combine solid colored traces and keep readings above the grid', async ({
  page,
}) => {
  await setup(page);
  await page.goto('/#/analysis/42');
  const picker = page.getByRole('button', { name: 'Choose sensor graph' });
  await picker.click();
  await page.getByRole('menuitemradio', { name: 'Encoders', exact: true }).click();
  await expect(page.locator('[data-channel-label]')).toHaveText('Encoders');
  await expect(
    page.getByRole('group', { name: 'Encoder wheels' }).getByRole('checkbox'),
  ).toHaveCount(6);
  const colors = await page
    .locator('[data-encoder-trace] path')
    .evaluateAll((paths) => paths.map((path) => getComputedStyle(path).stroke));
  expect(new Set(colors).size).toBe(6);
  for (const [index, wheel] of ['FL', 'FR', 'ML', 'MR', 'RL', 'RR'].entries()) {
    const checkbox = page.getByRole('checkbox', { name: `${wheel} wheel` });
    await expect(checkbox).toBeChecked();
    await expect(checkbox).toHaveClass('bag-checkbox');
    await expect(page.locator(`[data-encoder-value="encoder.${wheel}"]`)).toHaveCSS(
      'color',
      colors[index],
    );
    await expect(page.locator(`[data-encoder-trace="encoder.${wheel}"] path`)).toHaveCSS(
      'stroke-dasharray',
      'none',
    );
    await expect(page.locator(`[data-encoder-trace="encoder.${wheel}"] path`)).toHaveCSS(
      'stroke-width',
      '1.2px',
    );
  }
  const plot = page.getByRole('slider');
  await plot.press('ArrowRight');
  const positions = () =>
    page.locator('[data-encoder-value]').evaluateAll((items) =>
      items.map((el) => {
        const box = el.getBoundingClientRect();
        return { x: box.x, width: box.width };
      }),
    );
  const before = await positions();
  await plot.press('ArrowRight');
  expect(await positions()).toEqual(before);
  for (const wheel of ['ML', 'MR', 'RL', 'RR'])
    await page.getByRole('checkbox', { name: `${wheel} wheel` }).uncheck();
  await expect(page.locator('[data-encoder-trace]')).toHaveCount(2);
  await expect(page.locator('[data-encoder-value]')).toHaveCount(2);
  await expect(page.locator('.timeline-reading-label')).toHaveText(['FL', 'FR']);
  const box = (await plot.boundingBox())!;
  await page.mouse.move(box.x + box.width / 3, box.y + 80);
  await expect(page.locator('.chart-tooltip strong')).toHaveText(['19.000', '5.000']);
  await expect(plot).toHaveAttribute('aria-valuenow', '2');
  await page.mouse.move(0, 0);
  const readings = page.getByRole('group', { name: 'Wheel encoder readings' });
  expect(
    await readings.evaluate((el) => el.parentElement?.hasAttribute('data-timeline-plot')),
  ).toBe(true);
  await page
    .locator('.analysis-timeline')
    .screenshot({ path: test.info().outputPath('encoder-controls.png') });
  await picker.click();
  await page.getByRole('menuitemradio', { name: 'Angular velocity', exact: true }).click();
  await picker.click();
  await page.getByRole('menuitemradio', { name: 'Encoders', exact: true }).click();
  await expect(page.locator('[data-encoder-trace]')).toHaveCount(2);
  for (const wheel of ['FL', 'FR'])
    await page.getByRole('checkbox', { name: `${wheel} wheel` }).uncheck();
  await expect(
    page.locator('[data-encoder-trace], [data-encoder-value], .timeline-grid text'),
  ).toHaveCount(0);
  await expect(page.locator('.timeline-grid line')).toHaveCount(5);
});
