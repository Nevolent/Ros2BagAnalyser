import { test, expect } from '@playwright/test';

test.use({ timezoneId: 'America/Los_Angeles' });

const names = [
  'bunker_lidar_mapping_run_03_2025-12-29_09-45-00.bag',
  'outdoor_lidar_camera_calibration_2025-12-28_11-08-00.bag',
  'lunar_testing_obstacle_avoidance_2025-12-27_10-14-00.bag',
  'sensor_sync_validation_2025-12-26_08-30-00.bag',
];

test('progress ticks, pauses elapsed time, loops, and asks before cancellation', async ({
  page,
}) => {
  await page.clock.install();
  await page.goto('/?demo=1#/processing');
  const progress = page.getByRole('progressbar');
  await expect(progress).toHaveAttribute('aria-valuenow', '22');
  await page.clock.runFor(4000);
  await expect(page.locator('[data-processing-elapsed]')).toHaveText('0:52');
  await expect(progress).toHaveAttribute('aria-valuenow', '24');
  await page.getByRole('button', { name: 'Pause processing', exact: true }).click();
  await expect(page.locator('[data-processing-status]')).toBeEmpty();
  await page.clock.runFor(10_000);
  await expect(page.locator('[data-processing-elapsed]')).toHaveText('0:52');
  await expect(progress).toHaveAttribute('aria-valuenow', '24');
  await page.getByRole('button', { name: 'Resume processing', exact: true }).click();
  await page.clock.runFor(169_000);
  await expect(progress).toHaveAttribute('aria-valuenow', '100');
  await page.clock.runFor(1000);
  await expect(progress).toHaveAttribute('aria-valuenow', '0');
  await page.getByRole('button', { name: 'Cancel processing', exact: true }).click();
  const dialog = page.getByRole('dialog', { name: 'Cancel processing?' });
  await expect(dialog).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('button', { name: 'Cancel processing', exact: true })).toBeFocused();
  await page.clock.runFor(1000);
  await expect(page.locator('[data-processing-elapsed]')).toHaveText('0:01');
  await page.getByRole('button', { name: 'Cancel processing', exact: true }).click();
  await dialog.getByRole('button', { name: 'Cancel job', exact: true }).click();
  await page.clock.runFor(4000);
  await expect(page.locator('[data-processing-elapsed]')).toHaveText('0:01');
  await expect(page.locator('[data-processing-status]')).toHaveText('Cancelled');
  await page.getByRole('link', { name: 'Recordings', exact: true }).click();
  await expect(page.locator('.processing-confirm-dialog')).toHaveCount(0);
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await expect(page.locator('[data-processing-status]')).toHaveText('Cancelled');
});

test('queue supports confirmed bulk cancellation without reorder controls', async ({ page }) => {
  await page.goto('/?demo=1#/processing');
  const rows = page.locator('.bag-table tbody .bag-name');
  await page.getByRole('checkbox', { name: `Select ${names[1]}`, exact: true }).check();
  await page.getByRole('checkbox', { name: `Select ${names[2]}`, exact: true }).check();
  await expect(page.getByRole('checkbox', { name: 'Select all queued jobs' })).toHaveJSProperty(
    'indeterminate',
    true,
  );
  await expect(page.getByRole('button', { name: /Move earlier|Move later/ })).toHaveCount(0);
  await expect(rows).toHaveText(names);
  await page.getByRole('button', { name: 'Cancel 2 selected', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Keep in queue' })).toHaveCSS(
    'text-decoration-line',
    'none',
  );
  await page.getByRole('button', { name: 'Keep in queue' }).click();
  await expect(page.locator('.bag-table-scroll')).toHaveCSS('outline-style', 'none');
  await expect(rows).toHaveCount(4);
  await page.getByRole('button', { name: 'Cancel 2 selected', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel 2 jobs' }).click();
  await expect(rows).toHaveText([names[0], names[3]]);
  await page.getByRole('checkbox', { name: 'Select all queued jobs' }).check();
  await expect(page.getByRole('button', { name: /Move earlier|Move later/ })).toHaveCount(0);
});

test('failures retry only failed outputs and history stays read-only without tab resizing', async ({
  page,
}) => {
  await page.goto('/?demo=1#/processing');
  const failureTab = page.getByRole('button', { name: 'Failures', exact: true });
  const before = await failureTab.boundingBox();
  await failureTab.click();
  expect(await failureTab.boundingBox()).toEqual(before);
  await expect(page.getByRole('columnheader')).toHaveText([
    '',
    'Name',
    'Failed outputs',
    'Error code',
    'Actions',
  ]);
  await expect(page.getByText('E_RENDER_TIMEOUT', { exact: true })).toBeVisible();
  const failedName = await page.locator('.bag-table tbody .bag-name').first().textContent();
  await page.locator('.bag-table tbody [data-job-action="retry"]').first().click();
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(2);
  await page.getByRole('checkbox', { name: 'Select all failed jobs' }).check();
  await page.getByRole('button', { name: 'Retry 2 selected', exact: true }).click();
  await expect(page.getByText('No failed jobs.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Queue', exact: true }).click();
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(7);
  const retried = page.locator('.bag-table tbody tr').filter({ hasText: failedName! });
  await expect(retried.locator('td').nth(3)).toHaveText('1');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await expect(page.getByRole('columnheader')).toHaveText([
    'Name',
    'Completed',
    'Runtime',
    'Size',
    'Outputs',
  ]);
  await expect(page.locator('.bag-table tbody input,.bag-table tbody button')).toHaveCount(0);
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(4);
  await expect(page.getByRole('searchbox')).toHaveCount(0);
});

test('demo ready estimates remain relative', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-09-20T09:00:00Z') });
  await page.goto('/?demo=1#/processing');
  const firstReady = page.locator('.bag-table tbody tr').first().locator('[data-ready-in]');
  await expect(firstReady).toHaveText('8 min');
  await expect(page.locator('[data-ready-in]')).toHaveCount(4);
});

test('searches share exact geometry and table headers match the recordings panel', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  const metrics = await page.locator('.search-field').evaluateAll((fields) =>
    fields.map((field) => {
      const input = field.querySelector('input')!;
      const icon = field.querySelector('svg')!;
      return {
        height: field.getBoundingClientRect().height,
        font: getComputedStyle(input).font,
        icon: icon.getBoundingClientRect().height,
        stroke: icon.getAttribute('stroke-width'),
        background: getComputedStyle(field).backgroundColor,
      };
    }),
  );
  expect(metrics).toHaveLength(2);
  expect(metrics[0]).toEqual(metrics[1]);
  const colors = await page.evaluate(() => ({
    panel: getComputedStyle(document.querySelector('.data-table-panel')!).backgroundColor,
    header: getComputedStyle(document.querySelector('.bag-table thead th')!).backgroundColor,
  }));
  expect(colors.panel).toBe(colors.header);
  const scan = await page
    .getByRole('button', { name: 'Rescan Archive', exact: true })
    .boundingBox();
  expect(scan!.height).toBe(30);
  for (const route of ['Recordings', 'Analysis', 'Processing']) {
    await page.getByRole('link', { name: route, exact: true }).click();
    await expect(page.getByRole('heading', { name: route, exact: true, level: 1 })).toBeVisible();
    expect((await page.locator('.page-header').boundingBox())!.height).toBe(30);
  }
});

for (const width of [390, 768, 1440]) {
  test(`processing reuses recordings scrolling at ${width}px`, async ({ page }) => {
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/?demo=1');
    await page.getByRole('checkbox', { name: 'Select all visible bags' }).check();
    await page.getByRole('button', { name: 'Prepare Selected' }).click();
    await page.getByRole('checkbox', { name: 'Go to Processing' }).check();
    await page.getByRole('button', { name: 'Confirm', exact: true }).click();
    await expect(page.locator('.bag-table tbody tr')).toHaveCount(211);
    await page.locator('.bag-table-scroll').evaluate((el) => {
      el.scrollTop = el.scrollHeight;
    });
    await expect(page.getByRole('columnheader', { name: 'Name', exact: true })).toBeInViewport();
    await expect(page.getByRole('button', { name: 'Queue', exact: true })).toBeInViewport();
    await expect(page.locator('.bag-table tbody tr').last()).toBeInViewport();
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <= innerWidth &&
          document.documentElement.scrollHeight <= innerHeight,
      ),
    ).toBe(true);
    await page.getByRole('checkbox', { name: 'Select all queued jobs' }).check();
    await expect(page.getByRole('button', { name: 'Cancel 211 selected' })).toBeInViewport();
  });
}

test('failure summaries keep equal heights and full errors wrap in a compact detail dialog', async ({
  page,
}) => {
  await page.goto('/?demo=1#/processing');
  await page.getByRole('button', { name: 'Failures', exact: true }).click();
  expect(
    await page
      .locator('.bag-table tbody tr')
      .evaluateAll((rows) => rows.map((row) => row.getBoundingClientRect().height)),
  ).toEqual([44, 44, 44]);
  await page
    .locator('.bag-table tbody tr')
    .nth(1)
    .getByRole('button', { name: /View full error details/ })
    .click();
  const details = page.getByRole('dialog', { name: 'Failed outputs', exact: true });
  await expect(details.getByRole('listitem')).toHaveCount(2);
  await expect(details.getByText(/E_TRANSFORM_LOOKUP_EXTRAPOLATION/)).toBeVisible();
  await expect(details.getByText(/received bayer_rggb16/)).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await details.evaluate((el) => el.scrollWidth <= el.clientWidth)).toBe(true);
  await expect(details.getByRole('button', { name: 'Done' })).toBeInViewport();
  await details.getByRole('button', { name: 'Done' }).click();
  await expect(details).not.toBeVisible();
  await expect(page.locator('.bag-table-scroll')).toHaveCSS('outline-style', 'none');
});
