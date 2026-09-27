import { test, expect } from '@playwright/test';
import { apiFixture, job, diagnostic } from './api-fixture';

test('folders start open and recordings controls and scroll survive navigation', async ({
  page,
}) => {
  await page.goto('/?demo=1');
  await expect(page.getByRole('treeitem')).toHaveCount(30);
  await page.getByRole('button', { name: 'Collapse Bunker', exact: true }).click();
  await page.getByRole('searchbox', { name: 'Search recordings', exact: true }).fill('lunar');
  await page.getByRole('columnheader', { name: 'Name', exact: true }).getByRole('button').click();
  await page.locator('.bag-table tbody tr:visible input').first().check();
  const viewport = page.getByRole('region', { name: 'ROS bags', exact: true });
  await viewport.evaluate((el) => {
    el.scrollTop = 300;
  });
  await expect.poll(() => viewport.evaluate((el) => el.scrollTop)).toBe(300);
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await page.getByRole('link', { name: 'Recordings', exact: true }).click();
  await expect(page.getByRole('searchbox', { name: 'Search recordings', exact: true })).toHaveValue(
    'lunar',
  );
  await expect(page.getByRole('treeitem', { name: 'Bunker', exact: true })).toHaveAttribute(
    'aria-expanded',
    'false',
  );
  await expect(page.getByRole('columnheader', { name: 'Name', exact: true })).toHaveAttribute(
    'aria-sort',
    'ascending',
  );
  await expect(page.locator('.bag-table tbody input:checked')).toHaveCount(1);
  await expect.poll(() => viewport.evaluate((el) => el.scrollTop)).toBe(300);
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await expect(page.getByRole('button', { name: 'History', exact: true })).toHaveAttribute(
    'aria-pressed',
    'true',
  );
});

test('analysis remembers channel, time, zoom and details while stopping hidden playback', async ({
  page,
}) => {
  await page.goto('/?demo=1#/analysis');
  await page.getByRole('button', { name: 'Choose sensor graph' }).click();
  await page.getByRole('menuitemradio', { name: 'linear_acceleration.z', exact: true }).click();
  const plot = page.getByRole('slider');
  await plot.press('ArrowRight');
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  const end = await page.locator('[data-timeline-end]').textContent();
  await page.getByRole('button', { name: 'Collapse recording details' }).click();
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await page.getByRole('link', { name: 'Analysis', exact: true }).click();
  await expect(page.locator('[data-channel-label]')).toHaveText('linear_acceleration.z');
  await expect(plot).toHaveAttribute('aria-valuenow', '1');
  await expect(page.locator('[data-timeline-end]')).toHaveText(end!);
  await expect(page.getByRole('button', { name: 'Expand recording details' })).toBeVisible();
});

test('cached recordings remain visible without a loading overlay during a delayed refresh', async ({
  page,
}) => {
  const api = await apiFixture(page);
  await page.goto('/');
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(3);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.override = async (route, path) => {
    if (path !== '/api/v1/catalog') return false;
    await pending;
    await route.fulfill({ json: api.catalog });
    return true;
  };
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await page.getByRole('link', { name: 'Recordings', exact: true }).click();
  await expect(page.locator('.bag-table tbody tr:visible')).toHaveCount(3);
  await expect(page.getByText('Loading recordings…', { exact: true })).toHaveCount(0);
  await expect(page.locator('[data-bag-empty]')).toBeHidden();
  release();
});

test('background preparation errors follow navigation and can be dismissed', async ({ page }) => {
  const api = await apiFixture(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.override = async (route, path) => {
    if (!path.endsWith('/prepare')) return false;
    await pending;
    await route.fulfill({
      status: 503,
      json: { detail: { message: 'Preparation service unavailable.' } },
    });
    return true;
  };
  await page.goto('/');
  await page.getByRole('checkbox', { name: 'Select recording-42', exact: true }).check();
  await page.getByRole('button', { name: 'Prepare Selected' }).click();
  await page.getByRole('checkbox', { name: 'Go to Processing' }).check();
  await page.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page).toHaveURL(/#\/processing$/);
  release();
  await expect(page.getByRole('alert')).toContainText('Preparation service unavailable.');
  await page.getByRole('button', { name: 'Dismiss error' }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
});

test('active cancellation closes immediately and restores the card on server failure', async ({
  page,
}) => {
  const api = await apiFixture(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.override = async (route, path) => {
    if (!path.endsWith('/jobs/cancel')) return false;
    await pending;
    await route.fulfill({ status: 503, json: { detail: { message: 'Cancellation failed.' } } });
    return true;
  };
  await page.goto('/#/processing');
  await page.getByRole('button', { name: 'Cancel processing', exact: true }).click();
  await page.getByRole('button', { name: 'Cancel job', exact: true }).click();
  await expect(page.getByRole('dialog')).toBeHidden();
  await expect(page.locator('.processing-job')).toHaveCount(0);
  release();
  await expect(page.getByRole('alert')).toContainText('Cancellation failed.');
  await expect(page.getByRole('button', { name: 'Cancel processing', exact: true })).toBeVisible();
});

test('all processing pages load and failed recordings retain successful siblings and navigation', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.active = null;
  api.queue = [];
  const calls: string[] = [];
  api.override = async (route, path) => {
    if (path !== '/api/v1/processing/jobs') return false;
    const url = new URL(route.request().url());
    const view = url.searchParams.get('view')!;
    const second = url.searchParams.get('cursor') === `${view}+page==`;
    calls.push(`${view}:${second}`);
    const item = {
      ...job(second ? 101 : 100, second ? 'imu_series' : 'front_preview'),
      recording_id: view === 'queued' ? (second ? 71 : 70) : 42,
      recording_name: 'recording-42',
      state: view === 'failed' ? 'failed' : view === 'history' ? 'succeeded' : 'queued',
      ...(view === 'failed' ? { kind: 'topdown_preview' as const, diagnostic } : {}),
      finished_at: '2026-09-24T10:01:00Z',
    };
    await route.fulfill({
      json: {
        items: view === 'failed' && second ? [] : [item],
        next_cursor: second ? null : `${view}+page==`,
      },
    });
    return true;
  };
  await page.goto('/#/processing');
  await expect(page.locator('.processing-job')).toHaveCount(0);
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(2);
  expect(calls).toEqual(expect.arrayContaining(['queued:true', 'failed:true', 'history:true']));
  await page.getByRole('button', { name: 'Failures', exact: true }).click();
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(1);
  await expect(page.locator('.bag-table tbody tr')).toContainText('1 of 3');
  await page.getByRole('button', { name: 'History', exact: true }).click();
  await expect(page.getByText('No completed jobs yet.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Failures', exact: true }).click();
  await page.getByRole('link', { name: 'recording-42', exact: true }).click();
  await expect(page).toHaveURL(/#\/analysis\/42$/);
  await expect(page.locator('.analysis-recording-name')).toHaveText('recording-42');
});

test('optional sources show missing or unavailable without redundant errors', async ({ page }) => {
  const api = await apiFixture(page);
  api.recording.outputs = [
    {
      kind: 'front_preview',
      state: 'unavailable',
      diagnostic: { code: 'front_topic_unavailable', message: 'No camera topic.' },
    },
    {
      kind: 'topdown_preview',
      state: 'unavailable',
      diagnostic: { code: 'topdown_video_unavailable', message: 'No top-down video.' },
    },
    {
      kind: 'imu_series',
      state: 'unavailable',
      diagnostic: { code: 'imu_topic_unavailable', message: 'No IMU topic.' },
    },
  ];
  for (const role of ['topdown_video', 'topdown_timestamps'])
    api.recording.components.push({
      role,
      condition: 'missing',
      file_name: null,
      size_bytes: null,
      diagnostic: { code: `${role}_missing`, message: 'Expected source missing.' },
    });
  await page.goto('/#/analysis/42');
  await expect(
    page.locator('.recording-assets .status-muted').filter({ hasText: 'Unavailable' }),
  ).toHaveCount(3);
  await expect(
    page.locator('.recording-assets .status-muted').filter({ hasText: 'Missing' }),
  ).toHaveCount(2);
  await expect(page.locator('.recording-errors')).toHaveCount(0);
  api.recording.outputs[2] = { kind: 'imu_series', state: 'failed', diagnostic };
  await expect(page.locator('.recording-errors')).toContainText(diagnostic.message);
});

test('scrubbing beyond the graph never selects page text and the visual tail fills the timeline', async ({
  page,
}) => {
  await apiFixture(page);
  await page.goto('/#/analysis/42');
  const plot = page.getByRole('slider');
  await expect(page.locator('[data-timeline-value]')).toBeVisible();
  const box = (await plot.boundingBox())!;
  const end = await page
    .locator('.timeline-line')
    .evaluate((el: SVGPathElement) => el.getPointAtLength(el.getTotalLength()).x);
  expect(end).toBeCloseTo(box.width, 1);
  await page.mouse.move(box.x + box.width * 0.8, box.y + 60);
  await page.mouse.down();
  await page.mouse.move(0, 0, { steps: 8 });
  await page.mouse.up();
  expect(await page.evaluate(() => window.getSelection()?.toString())).toBe('');
  await expect(plot).toHaveAttribute('aria-valuenow', '0');
  await plot.press('End');
  await expect(page.locator('[data-timeline-value]')).toHaveText('—');
  await expect(page.locator('.timeline-cursor circle')).toHaveCount(0);
});

test('dense six-axis telemetry scrubs with decoded cameras without rebuilding the trace', async ({
  page,
}, testInfo) => {
  const { readFileSync } = await import('node:fs');
  const source = readFileSync('../tools/serve_frontend_mock.py', 'utf8');
  const video = Buffer.from(
    source.match(/MOCK_VIDEO = base64.b64decode\(\s*"([A-Za-z0-9+/=]+)"/)![1],
    'base64',
  );
  const api = await apiFixture(page);
  const count = 120_000;
  api.recording.duration_ns = '1000000000';
  api.recording.outputs.forEach((output) => {
    output.artifact!.coverage_start_ns = '0';
    output.artifact!.coverage_end_ns = '999991667';
  });
  api.imu.data.samples = Array.from({ length: count }, (_, i) => [
    String(Math.round((i * 1e9) / count)),
    ...Array.from({ length: 6 }, (_, axis) =>
      axis === 5 && i % 2 ? null : Math.sin(i / 100 + axis),
    ),
  ]);
  const artifact = api.imu.state.artifact;
  artifact.delivered_sample_count = String(count);
  artifact.coverage_start_ns = '0';
  artifact.coverage_end_ns = String(api.imu.data.samples.at(-1)![0]);
  for (let axis = 0; axis < 6; axis++) {
    const finite = api.imu.data.samples
      .map((row) => row[axis + 1] as number | null)
      .filter((value): value is number => value !== null);
    Object.assign(artifact.series[axis], {
      finite_sample_count: String(finite.length),
      non_finite_sample_count: String(count - finite.length),
      minimum_value: finite.reduce((a, b) => Math.min(a, b), Infinity),
      maximum_value: finite.reduce((a, b) => Math.max(a, b), -Infinity),
    });
  }
  api.override = async (route, path) => {
    if (!path.includes('/media/')) return false;
    const range = route
      .request()
      .headers()
      .range?.match(/^bytes=(\d+)-(\d*)$/);
    const start = range ? Number(range[1]) : 0;
    const end = range?.[2] ? Number(range[2]) : video.length - 1;
    await route.fulfill({
      status: range ? 206 : 200,
      contentType: 'video/mp4',
      headers: {
        'Accept-Ranges': 'bytes',
        ...(range ? { 'Content-Range': `bytes ${start}-${end}/${video.length}` } : {}),
      },
      body: video.subarray(start, end + 1),
    });
    return true;
  };
  await page.goto('/#/analysis/42');
  const plot = page.getByRole('slider');
  const camera = page.locator('.analysis-camera-front video');
  await expect(page.locator('[data-channel-label]')).toHaveText('angular_velocity.z');
  await expect
    .poll(() => camera.evaluate((el: HTMLVideoElement) => el.readyState))
    .toBeGreaterThanOrEqual(2);
  for (const name of [
    'angular_velocity.x',
    'angular_velocity.y',
    'angular_velocity.z',
    'linear_acceleration.x',
    'linear_acceleration.y',
    'linear_acceleration.z',
  ]) {
    await page.getByRole('button', { name: 'Choose sensor graph' }).click();
    await page.getByRole('menuitemradio', { name, exact: true }).click();
  }
  const box = (await plot.boundingBox())!;
  expect(await page.locator('[data-timeline-single-sample]').count()).toBeLessThanOrEqual(
    Math.ceil(box.width),
  );
  await page.evaluate(() => {
    const metrics = { frames: [] as number[], changes: 0, running: true };
    (window as any).scrubMetrics = metrics;
    new MutationObserver((records) => {
      metrics.changes += records.length;
    }).observe(document.querySelector('.timeline-line')!, { attributes: true });
    let last = performance.now();
    const tick = (now: number) => {
      metrics.frames.push(now - last);
      last = now;
      if (metrics.running) requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  });
  await page.mouse.move(box.x + box.width * 0.2, box.y + 50);
  await page.mouse.down();
  for (let i = 0; i < 4; i++)
    await page.mouse.move(box.x + box.width * (i % 2 ? 0.2 : 0.8), box.y + 50, { steps: 12 });
  await page.mouse.up();
  await expect
    .poll(() => camera.evaluate((el: HTMLVideoElement) => el.currentTime))
    .toBeCloseTo(0.2, 1);
  await expect(camera).toHaveCSS('visibility', 'visible');
  const metrics = await page.evaluate(() => {
    const data = (window as any).scrubMetrics;
    data.running = false;
    const frames = data.frames.sort((a: number, b: number) => a - b);
    return {
      frames: frames.length,
      p95Ms: frames[Math.floor(frames.length * 0.95)],
      traceChanges: data.changes,
    };
  });
  await testInfo.attach('scrub-performance', {
    body: JSON.stringify(metrics),
    contentType: 'application/json',
  });
  expect(metrics.traceChanges).toBe(0);
  expect(metrics.frames).toBeGreaterThan(20);
  expect(metrics.p95Ms).toBeLessThan(100);
  await page.getByRole('button', { name: 'Play timeline', exact: true }).click();
  await expect.poll(() => camera.evaluate((el: HTMLVideoElement) => el.paused)).toBe(false);
});

test('failure counts include ready outputs while a sibling is still processing', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.queue = [];
  api.history = []; // The history API withholds success until active siblings finish.
  api.failures = [{ ...job(19, 'topdown_preview'), recording_id: 42, state: 'failed', diagnostic }];
  api.recording.outputs[0] = {
    kind: 'front_preview',
    state: 'processing',
    job_id: 9,
    diagnostic: null,
  };
  api.recording.outputs[1] = { kind: 'topdown_preview', state: 'failed', job_id: 19, diagnostic };
  await page.goto('/#/processing');
  await page.getByRole('button', { name: 'Failures', exact: true }).click();
  await expect(page.locator('.bag-table tbody tr')).toContainText('1 of 3');
  await page.getByRole('button', { name: 'Retry recording-42', exact: true }).click();
  await expect.poll(() => api.posts.length).toBe(1);
  expect(api.posts[0].body).toEqual({ job_ids: [19] });
});
