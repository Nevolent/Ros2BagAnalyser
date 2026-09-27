import { test, expect } from '@playwright/test';
import { apiFixture, detail, job, diagnostic } from './api-fixture';

test('live catalog filters, real folders, red review, selection and explicit scan', async ({
  page,
}) => {
  const api = await apiFixture(page);
  await page.goto('/');
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(3);
  expect(api.posts).toEqual([]);
  await expect(page.locator('[data-folder]')).toHaveCount(2);
  await expect(page.locator('[data-folder="experiments"]')).toBeVisible();
  await page.getByRole('button', { name: 'Filter by health' }).click();
  const reviewOption = page.getByRole('menuitemradio', { name: 'Review', exact: true });
  const reviewColor = await page.evaluate(() => {
    const probe = document.createElement('span');
    probe.style.color = 'var(--status-error)';
    document.body.append(probe);
    const color = getComputedStyle(probe).color;
    probe.remove();
    return color;
  });
  const normalFilterColor = await page
    .getByRole('button', { name: 'Filter by health' })
    .evaluate((element) => getComputedStyle(element).color);
  const normalOptionColor = await page
    .getByRole('menuitemradio', { name: 'Readable' })
    .evaluate((element) => getComputedStyle(element).color);
  await expect(reviewOption).toHaveCSS('color', normalOptionColor);
  await reviewOption.click();
  await expect(page.getByRole('button', { name: 'Filter by health' })).toHaveCSS(
    'color',
    normalFilterColor,
  );
  const rows = page.locator('.bag-table tbody tr:visible');
  await expect(rows).toHaveCount(1);
  await expect(rows.getByText('Review', { exact: true })).toHaveCSS('color', reviewColor);
  await page.getByRole('button', { name: 'Filter by health' }).click();
  await page.getByRole('menuitemradio', { name: 'Health', exact: true }).click();
  await page.getByRole('button', { name: 'Filter by analysis' }).click();
  await page.getByRole('menuitemradio', { name: 'Ready', exact: true }).click();
  await expect(rows).toHaveCount(2);
  await expect(rows.filter({ hasText: 'recording-44' })).toHaveCount(1);
  await page.getByRole('button', { name: 'Rescan Archive', exact: true }).click();
  await expect.poll(() => api.posts.length).toBe(1);
  expect(api.posts[0].path).toBe('/api/v1/catalog/rescan');
});

test('prepare dismisses immediately, reports background failures and never fabricates a queued count', async ({
  page,
}) => {
  const api = await apiFixture(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.override = async (route, path) => {
    if (!path.endsWith('/prepare')) return false;
    api.posts.push({ path, body: route.request().postDataJSON() });
    await pending;
    await route.fulfill({
      status: 503,
      json: { detail: { message: 'Worker storage unavailable.' } },
    });
    return true;
  };
  await page.goto('/');
  await page.getByRole('checkbox', { name: 'Select recording-42', exact: true }).check();
  await page.getByRole('button', { name: 'Prepare Selected' }).click();
  const dialog = page.getByRole('dialog', { name: 'Prepare recordings' });
  await dialog.getByRole('button', { name: 'Confirm' }).click();
  await expect(dialog).toBeHidden();
  release();
  await expect(page.getByRole('alert')).toHaveText('Worker storage unavailable.');
  expect(api.posts[0].body).toEqual({
    recording_ids: [42],
    output_kinds: ['front_preview', 'topdown_preview', 'imu_series'],
  });
  await expect(page.locator('.recordings-notice')).toHaveCount(0);
  api.override = null;
  await page.getByRole('button', { name: 'Prepare Selected' }).click();
  await dialog.getByRole('button', { name: 'Confirm' }).click();
  await expect(dialog).not.toBeVisible();
  await expect(
    page.getByRole('status').filter({ hasText: 'Preparation request completed.' }),
  ).toBeVisible();
});

test('processing uses stored time, unavailable estimates, durable controls and grouped output IDs', async ({
  page,
}) => {
  const api = await apiFixture(page);
  await page.goto('/#/processing');
  await expect(page.locator('[data-processing-elapsed]')).toHaveText('0:10');
  await expect(page.getByRole('progressbar')).not.toHaveAttribute('aria-valuenow');
  await expect(page.locator('[data-ready-in]')).toHaveText('Unavailable');
  await expect(
    page.getByRole('button', { name: /Pause processing|Resume processing/ }),
  ).toHaveCount(0);
  await page.getByRole('checkbox', { name: 'Select recording-42', exact: true }).check();
  await expect(page.getByRole('button', { name: 'Move up' })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel 1 selected' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel job', exact: true }).click();
  await expect(page.getByText('No queued jobs.', { exact: true })).toBeVisible();
  expect(api.posts.find((post) => post.path.endsWith('/jobs/cancel'))?.body).toEqual({
    job_ids: [10, 11],
  });
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await expect(page.locator('.bag-table tbody')).toContainText('1:05');
  await expect(page.locator('.bag-table tbody')).toContainText('2.00 KiB');
});

test('queue move posts grouped job IDs and displays the server order', async ({ page }) => {
  const api = await apiFixture(page);
  api.queue.push({
    ...job(20),
    recording_id: 46,
    recording_name: 'recording-46',
  });
  api.override = async (route, path) => {
    if (path !== '/api/v1/processing/jobs/reorder') return false;
    api.posts.push({ path, body: route.request().postDataJSON() });
    api.queue = [api.queue[2], ...api.queue.slice(0, 2)];
    await route.fulfill({ json: { items: [{ outcome: 'reordered' }] } });
    return true;
  };
  await page.goto('/#/processing');
  await page.getByRole('checkbox', { name: 'Select recording-42', exact: true }).check();
  await page.getByRole('button', { name: 'Move down' }).click();
  await expect(page.locator('.bag-table tbody .bag-name')).toHaveText([
    'recording-46',
    'recording-42',
  ]);
  expect(api.posts[0]).toEqual({
    path: '/api/v1/processing/jobs/reorder',
    body: { job_ids: [10, 11], direction: 'later' },
  });
});

test('estimated progress ticks between polls and stops at 99 when the estimate is exceeded', async ({
  page,
}) => {
  await page.clock.install();
  const api = await apiFixture(page);
  api.active!.estimate = { status: 'available', estimated_total_ms: 15000 };
  api.override = async (route, path) => {
    if (path !== '/api/v1/processing/overview') return false;
    await route.fulfill({
      json: {
        current: api.active,
        queue: api.queue,
        worker_online: true,
        recommended_poll_interval_ms: 30_000,
      },
    });
    return true;
  };
  await page.goto('/#/processing');
  await expect(page.locator('[data-processing-elapsed]')).toHaveText('0:10');
  await page.clock.runFor(2100);
  await expect(page.locator('[data-processing-elapsed]')).toHaveText('0:12');
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', /^8[0-6]$/);
  await page.clock.runFor(4000);
  await expect(page.getByRole('progressbar')).toHaveAttribute('aria-valuenow', '99');
  await expect(page.locator('[data-processing-percent]')).toHaveText('Estimate exceeded');
});

test('failed-output retry posts backend job IDs and errors stay plain text', async ({ page }) => {
  const api = await apiFixture(page);
  await page.goto('/#/processing');
  await page.getByRole('button', { name: 'Failures', exact: true }).click();
  await page.locator('[data-failure-details]').click();
  await expect(page.getByRole('dialog')).toContainText(diagnostic.message);
  await expect(page.getByRole('dialog').locator('script')).toHaveCount(0);
  await page.getByRole('dialog').getByRole('button', { name: 'Done' }).click();
  await page.getByRole('button', { name: 'Retry recording-42', exact: true }).click();
  await expect.poll(() => api.posts.length).toBe(1);
  expect(api.posts[0].body).toEqual({ job_ids: [12] });
  await expect(page.getByText('No failed jobs.', { exact: true })).toBeVisible();
});

test('analysis opens actual recording with irregular IMU time, last duplicate, null gaps and coverage', async ({
  page,
}) => {
  await apiFixture(page);
  await page.goto('/');
  await page.getByRole('link', { name: 'recording-42', exact: true }).click();
  await expect(page).toHaveURL(/#\/analysis\/42$/);
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  await expect(plot).toHaveAttribute('aria-valuemax', '6');
  await expect(page.locator('[data-timeline-value]')).toHaveText('—');
  await plot.focus();
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('[data-timeline-value]')).toHaveText('1.000');
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('[data-timeline-value]')).toHaveText('9.000');
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('[data-timeline-value]')).toHaveText('—');
  await page.keyboard.press('ArrowRight');
  await expect(page.locator('[data-timeline-value]')).toHaveText('4.000');
  await page.keyboard.press('End');
  await expect(page.locator('[data-timeline-value]')).toHaveText('—');
  expect((await page.locator('.timeline-line').getAttribute('d'))?.match(/M/g)?.length).toBe(2);
  await expect(page.locator('[data-timeline-single-sample]')).toHaveCount(0);
  await expect(page.locator('.recording-errors')).toContainText('camera could not be loaded.');
});

test('queued, processing and unavailable states use simple text with errors at the bottom', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.recording = {
    ...detail(),
    analysis_state: 'processing',
    diagnostic,
    outputs: [
      { kind: 'front_preview', state: 'processing', diagnostic: null },
      { kind: 'topdown_preview', state: 'queued', diagnostic: null },
      { kind: 'imu_series', state: 'unavailable', diagnostic },
    ],
  };
  await page.goto('/#/analysis/42');
  await expect(page.getByText('This is currently processing.', { exact: true })).toBeVisible();
  await expect(page.getByText('This is currently queued.', { exact: true })).toBeVisible();
  await expect(page.locator('.timeline-state')).toHaveText('This output is unavailable.');
  await expect(page.getByRole('button', { name: /processing/i })).toHaveCount(0);
  await expect(page.locator('.recording-details-body > div > :last-child')).toHaveClass(
    'recording-errors',
  );
  await expect(page.locator('.recording-errors')).toContainText(diagnostic.message);
  await expect(page.locator('.recording-details-body script')).toHaveCount(0);
});

test('damaged recording without validated outputs keeps the clock but hides data labels', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.recording = {
    ...detail(),
    presentation_health: 'damaged',
    analysis_state: 'not_planned',
    outputs: [],
  };
  await page.goto('/#/analysis/42');
  const slider = page.getByRole('slider', { name: 'Recording timeline' });
  await expect(page.getByRole('button', { name: 'Play timeline', exact: true })).toBeEnabled();
  await expect(page.locator('.timeline-state')).toHaveText('This output is unavailable.');
  await expect(page.locator('.timeline-axis')).toHaveCount(0);
  await expect(page.locator('.timeline-measurement')).toHaveCount(0);
  await expect(page.locator('.timeline-grid text')).toHaveCount(0);
  await slider.focus();
  await page.keyboard.press('End');
  await expect(slider).toHaveAttribute('aria-valuenow', '6');
  await expect(slider).toHaveAttribute('aria-valuetext', 'Recording position 6.0 of 6.0 seconds');
  await expect(page.locator('[data-selection-start], [data-selection-end]')).toHaveCount(0);
});

test('invalid artifact URLs and invalid telemetry never reach renderers', async ({ page }) => {
  const api = await apiFixture(page);
  api.recording.outputs[0].artifact!.url = 'https://example.invalid/private-media';
  api.imu.data.samples[1][0] = '5000000000';
  await page.goto('/#/analysis/42');
  await expect(page.locator('.recording-errors')).toContainText('Invalid artifact identity or URL');
  await expect(page.locator('.recording-errors')).toContainText('timestamps are not ordered');
  await expect(page.locator('.analysis-camera-front video')).toHaveCount(0);
  await expect(page.locator('[data-timeline-value]')).toHaveCount(0);
});

test('loading, offline catalog and missing recording never fall back to demo data', async ({
  page,
}) => {
  const api = await apiFixture(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.override = async (route, path) => {
    if (path !== '/api/v1/catalog') return false;
    await pending;
    await route.fulfill({ status: 503, json: { detail: { message: 'Catalog unavailable.' } } });
    return true;
  };
  await page.goto('/');
  await expect(page.getByText('Loading recordings…', { exact: true })).toBeVisible();
  release();
  await expect(page.getByRole('alert')).toHaveText('Catalog unavailable.');
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(0);
  await page.goto('/#/analysis/999');
  await expect(page.getByRole('alert')).toHaveText('Recording not found.');
  expect(api.posts).toEqual([]);
});

test('pagination loads all pages automatically and follows opaque API cursors', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.override = async (route, path) => {
    const url = new URL(route.request().url());
    if (path !== '/api/v1/processing/jobs' || url.searchParams.get('view') !== 'history')
      return false;
    const next = url.searchParams.has('cursor');
    await route.fulfill({
      json: {
        items: [
          {
            ...job(next ? 101 : 100),
            recording_id: next ? 101 : 100,
            recording_name: next ? 'older-recording' : 'recent-recording',
            finished_at: '2026-09-24T10:01:00Z',
            state: 'succeeded',
          },
        ],
        next_cursor: next ? null : 'opaque+cursor==',
      },
    });
    return true;
  };
  await page.goto('/#/processing');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(2);
  await expect(page.getByRole('button', { name: 'Load more' })).toHaveCount(0);
});

test('camera videos follow the shared clock with measured offsets and clear outside coverage', async ({
  page,
}) => {
  const { readFileSync } = await import('node:fs');
  const source = readFileSync('../tools/serve_frontend_mock.py', 'utf8');
  const encoded = source.match(/MOCK_VIDEO = base64.b64decode\(\s*"([A-Za-z0-9+/=]+)"/)![1];
  const api = await apiFixture(page);
  api.recording.outputs[0].artifact!.coverage_end_ns = '2000000000';
  api.recording.outputs[1].artifact!.coverage_start_ns = '2000000000';
  api.recording.outputs[1].artifact!.coverage_end_ns = '3000000000';
  api.override = async (route, path) => {
    if (!path.includes('/media/')) return false;
    const media = Buffer.from(encoded, 'base64');
    const range = route
      .request()
      .headers()
      .range?.match(/^bytes=(\d+)-(\d*)$/);
    const start = range ? Number(range[1]) : 0;
    const end = range?.[2] ? Number(range[2]) : media.length - 1;
    await route.fulfill({
      status: range ? 206 : 200,
      contentType: 'video/mp4',
      headers: {
        'Accept-Ranges': 'bytes',
        ...(range ? { 'Content-Range': `bytes ${start}-${end}/${media.length}` } : {}),
      },
      body: media.subarray(start, end + 1),
    });
    return true;
  };
  await page.goto('/#/analysis/42');
  const front = page.locator('.analysis-camera-front video');
  const top = page.locator('.analysis-camera-top video');
  await expect
    .poll(() => front.evaluate((video: HTMLVideoElement) => video.readyState))
    .toBeGreaterThanOrEqual(2);
  await expect(page.locator('.analysis-camera-front [data-camera-state]')).toHaveText(
    'Outside camera coverage.',
  );
  const plot = page.getByRole('slider', { name: 'Recording timeline' });
  const box = await plot.boundingBox();
  await plot.click({ position: { x: box!.width / 4, y: 50 } });
  await expect
    .poll(() => front.evaluate((video: HTMLVideoElement) => video.currentTime))
    .toBeCloseTo(0.5, 1);
  await expect(page.locator('.analysis-camera-front [data-camera-state]')).toBeHidden();
  await front.evaluate((video: HTMLVideoElement) => {
    Object.defineProperty(video, 'readyState', { configurable: true, value: 1 });
    video.dispatchEvent(new Event('seeking'));
  });
  await expect(page.locator('.analysis-camera-front [data-camera-state]')).toBeHidden();
  await expect(front).toHaveCSS('visibility', 'visible');
  await front.evaluate((video: HTMLVideoElement) => {
    delete (video as HTMLVideoElement & { readyState?: number }).readyState;
    video.dispatchEvent(new Event('seeked'));
  });
  await expect(page.locator('.analysis-camera-top [data-camera-state]')).toHaveText(
    'Outside camera coverage.',
  );
  await page.getByRole('button', { name: 'Play timeline', exact: true }).click();
  await expect.poll(() => front.evaluate((video: HTMLVideoElement) => video.paused)).toBe(false);
  await expect
    .poll(() => top.evaluate((video: HTMLVideoElement) => video.currentTime))
    .toBeGreaterThan(0.1);
  await page.getByRole('button', { name: 'Pause timeline', exact: true }).click();
  await plot.focus();
  await page.keyboard.press('End');
  await expect(page.locator('.analysis-camera-top [data-camera-state]')).toHaveText(
    'Outside camera coverage.',
  );
  expect(await top.evaluate((video: HTMLVideoElement) => video.paused)).toBe(true);
  await page.getByRole('link', { name: 'Recordings', exact: true }).click();
  await expect(page.locator('video')).toHaveCount(0);
});

test('late recording responses cannot overwrite navigation and selected analysis can be revisited', async ({
  page,
}) => {
  const api = await apiFixture(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.override = async (route, path) => {
    if (path !== '/api/v1/recordings/43') return false;
    await pending;
    await route.fulfill({ json: detail(43) });
    return true;
  };
  await page.goto('/#/analysis/43');
  await expect(page.getByText('Loading recording…', { exact: true })).toBeVisible();
  await page.evaluate(() => {
    location.hash = '/analysis/42';
  });
  await expect(page.locator('.analysis-recording-name')).toHaveText('recording-42');
  release();
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await page.getByRole('link', { name: 'Analysis', exact: true }).click();
  await expect(page.locator('.analysis-recording-name')).toHaveText('recording-42');
});

test('optional missing top-down does not reject preparation and active cancellation includes remaining outputs', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.override = async (route, path) => {
    if (!path.endsWith('/prepare')) return false;
    await route.fulfill({
      json: {
        recordings: [
          {
            outputs: [
              { kind: 'front_preview', outcome: 'queued' },
              {
                kind: 'topdown_preview',
                outcome: 'unavailable',
                diagnostic: {
                  code: 'topdown_video_unavailable',
                  message: 'No optional top-down video.',
                },
              },
            ],
          },
        ],
      },
    });
    return true;
  };
  await page.goto('/');
  await page.getByRole('checkbox', { name: 'Select recording-42', exact: true }).check();
  await page.getByRole('button', { name: 'Prepare Selected' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  api.recording.outputs = [
    { kind: 'front_preview', state: 'processing', job_id: 9, diagnostic: null },
    { kind: 'topdown_preview', state: 'queued', job_id: 14, diagnostic: null },
    { kind: 'imu_series', state: 'queued', job_id: 15, diagnostic: null },
  ];
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await page.getByRole('button', { name: 'Cancel processing', exact: true }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Cancel job', exact: true }).click();
  await expect.poll(() => api.posts.length).toBe(1);
  expect(api.posts[0].body).toEqual({ job_ids: [9, 14, 15] });
});

test('preparation accepts one available output and reports when none can be prepared', async ({
  page,
}) => {
  const api = await apiFixture(page);
  let available = true;
  api.override = async (route, path) => {
    if (!path.endsWith('/prepare')) return false;
    await route.fulfill({
      json: {
        recordings: [
          {
            outputs: [
              {
                kind: 'front_preview',
                outcome: 'unavailable',
                diagnostic: { code: 'front_topic_unavailable', message: 'No front camera.' },
              },
              {
                kind: 'topdown_preview',
                outcome: 'unavailable',
                diagnostic: { code: 'topdown_video_unavailable', message: 'No top-down video.' },
              },
              available
                ? { kind: 'imu_series', outcome: 'queued' }
                : {
                    kind: 'imu_series',
                    outcome: 'unavailable',
                    diagnostic: { code: 'imu_topic_unavailable', message: 'No IMU topic.' },
                  },
            ],
          },
        ],
      },
    });
    return true;
  };
  await page.goto('/');
  await page.getByRole('checkbox', { name: 'Select recording-42', exact: true }).check();
  await page.getByRole('button', { name: 'Prepare Selected' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(
    page.getByRole('status').filter({ hasText: 'Preparation request completed.' }),
  ).toBeVisible();

  available = false;
  await page.getByRole('checkbox', { name: 'Select recording-42', exact: true }).check();
  await page.getByRole('button', { name: 'Prepare Selected' }).click();
  await page.getByRole('dialog').getByRole('button', { name: 'Confirm' }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page.getByRole('alert')).toContainText('No IMU topic.');
});

test('history combines completed outputs and queue uses cumulative server estimates', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.queue[0].queue_estimate = { status: 'available', ready_in_ms: 60000 };
  api.queue[1].queue_estimate = { status: 'available', ready_in_ms: 120000 };
  api.history.push({
    ...api.history[0],
    id: 16,
    kind: 'imu_series',
    runtime_ms: 30000,
    output_size_bytes: '2048',
  });
  await page.goto('/#/processing');
  await expect(page.locator('[data-ready-in]')).toHaveText('2 min');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(1);
  await expect(page.locator('.bag-table tbody tr')).toContainText('1:35');
  await expect(page.locator('.bag-table tbody tr')).toContainText('4.00 KiB');
  await expect(page.locator('.processing-history-outputs')).toHaveText('2');
});

test('zero-duration and camera-only recordings retain truthful controls', async ({ page }) => {
  const api = await apiFixture(page);
  api.recording = { ...detail(), duration_ns: '0', start_time_ns: null, outputs: [] };
  await page.goto('/#/analysis/42');
  await expect(page.getByRole('button', { name: 'Play timeline', exact: true })).toBeDisabled();
  await expect(page.locator('[data-timeline-value]')).toHaveCount(0);
  await expect(page.locator('.timeline-axis')).toHaveCount(0);
  await expect(page.locator('.recording-errors')).toContainText('zero duration');
  await expect(page.locator('[data-timeline-svg]')).not.toHaveAttribute('viewBox', /NaN/);
  api.recording = detail();
  api.recording.outputs[2] = { kind: 'imu_series', state: 'unavailable', diagnostic: null };
  await page.reload();
  await expect(page.getByRole('button', { name: 'Play timeline', exact: true })).toBeEnabled();
  await expect(page.locator('[data-channel-label]')).toHaveText('Recording timeline');
  await expect(page.locator('.timeline-axis')).toHaveCount(0);
  await expect(page.locator('.timeline-measurement')).toHaveCount(0);
  await page.getByRole('slider', { name: 'Recording timeline' }).focus();
  await page.keyboard.press('End');
  await expect(page.getByRole('slider')).toHaveAttribute('aria-valuenow', '6');
});

for (const width of [390, 1440]) {
  test(`live diagnostics fit the imported layout at ${width}px`, async ({ page }, testInfo) => {
    const api = await apiFixture(page);
    api.recording.diagnostic = {
      code: 'synthetic_error',
      message: 'A diagnostic with a long value: ' + 'x'.repeat(400),
    };
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/#/analysis/42');
    await expect(page.locator('.recording-errors')).toContainText('synthetic_error');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(
      true,
    );
    await page.screenshot({ path: testInfo.outputPath(`live-analysis-${width}.png`) });
    await page.keyboard.press('Control+k');
    await expect(page.getByRole('option')).toHaveCount(3);
  });
}

test('Ready in sorting uses cumulative server values without changing queue priority', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.queue[0].queue_estimate = { status: 'available', ready_in_ms: 60000 };
  api.queue[1].queue_estimate = { status: 'available', ready_in_ms: 120000 };
  api.queue.push({
    ...job(17),
    recording_id: 46,
    recording_name: 'later-recording',
    queue_estimate: { status: 'available', ready_in_ms: 180000 },
  });
  await page.goto('/#/processing');
  await expect(page.locator('[data-ready-in]')).toHaveText(['2 min', '3 min']);
  await page.getByRole('button', { name: 'Ready in', exact: true }).click();
  await page.getByRole('button', { name: 'Ready in', exact: true }).click();
  await expect(page.locator('[data-ready-in]')).toHaveText(['3 min', '2 min']);
  expect(api.posts).toEqual([]);
});

test('an open queued recording adopts newly available coverage and IMU channels', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.recording = {
    ...detail(),
    duration_ns: '0',
    outputs: [{ kind: 'imu_series', state: 'queued', diagnostic: null }],
  };
  await page.goto('/#/analysis/42');
  await expect(page.locator('.timeline-state')).toHaveText('This is currently queued.');
  api.imu.state.artifact.default_series_id = 'angular_velocity_x';
  const axis = api.imu.state.artifact.series[2];
  Object.assign(axis, {
    available: false,
    minimum_value: null,
    maximum_value: null,
    finite_sample_count: '0',
    non_finite_sample_count: '5',
  });
  api.imu.data.samples.forEach((row) => {
    row[3] = null;
  });
  api.recording = detail();
  await expect(page.locator('[data-channel-label]')).toHaveText('angular_velocity.x');
  await expect(page.locator('[data-timeline-end]')).toHaveText('1767083106.000');
  await expect(page.getByRole('button', { name: 'Play timeline', exact: true })).toBeEnabled();
});
