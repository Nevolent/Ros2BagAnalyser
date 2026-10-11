import { syntheticVideo } from './media-fixture';
import { test, expect } from '@playwright/test';
import { apiFixture } from './api-fixture';

test('sidebar tabs lead the panel; all topics are scrollable, safe and truncated', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.recording.topics = Array.from({ length: 180 }, (_, i) => ({
    name: i === 179 ? '/camera/<script>topic</script>' : '/robot/stream_' + i,
    message_type: i === 179 ? 'sensor_msgs/msg/Image' : 'sensor_msgs/msg/Imu',
    message_count: String(i * 100),
    serialization_format: 'cdr',
  }));
  api.recording.presentation_health = 'review';
  api.recording.diagnostic = {
    code: 'recording_time_gap',
    message: 'Possible missing data: a 15.1 s timestamp gap near 4.9 s.',
  };
  api.recording.timing = {
    status: 'complete',
    messages_checked: 100,
    origin_ns: api.recording.start_time_ns,
    gaps: [
      { topic: null, start_ns: '4900000000', end_ns: '20000000000', duration_ns: '15100000000' },
    ],
  };
  await page.goto('/#/recordings');
  await page.getByRole('searchbox', { name: 'Search recordings' }).fill('recording-42');
  const review = page.getByRole('button', { name: 'Review', exact: true });
  await review.focus();
  await expect(page.getByRole('tooltip')).toContainText('Possible missing data');
  await page.keyboard.press('Escape');
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  await page.goto('/#/analysis/42');
  await expect(page.getByRole('heading', { name: 'Recording details' })).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Timestamp inspection' })).toHaveCount(0);
  await expect(page.getByText('Rescan to check timestamps.')).toHaveCount(0);
  const health = page
    .getByRole('region', { name: 'Recording errors' })
    .getByText(api.recording.diagnostic.message, { exact: true });
  await expect(health).toBeVisible();
  await expect(health).toContainText('15.1 s timestamp gap');
  await expect(health).toHaveCSS('white-space', 'normal');
  await expect(health).toHaveCSS('overflow-wrap', 'anywhere');
  await page.getByRole('button', { name: 'Topics', exact: true }).click();
  await expect(page.getByRole('searchbox', { name: 'Search topics' })).toHaveCount(0);
  await expect(page.locator('.folder-heading .page-tab-count')).toHaveCount(0);
  await expect(page.locator('.folder-heading')).toContainText('Details');
  await expect(page.locator('.folder-heading')).toContainText('Topics');
  const list = page.getByRole('region', { name: 'Recording topics' });
  await expect(list.getByRole('listitem')).toHaveCount(180);
  const viewport = page.locator('.recording-topics-list');
  expect(await viewport.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await expect(list).toContainText('/camera/<script>topic</script>');
  expect(await list.locator('script').count()).toBe(0);
  const splitter = page.getByRole('separator', { name: 'Resize recording details' });
  await splitter.focus();
  await page.keyboard.press('ArrowRight');
  const topic = list.locator('code').last();
  await expect(topic).toHaveCSS('white-space', 'nowrap');
  await expect(topic).toHaveCSS('text-overflow', 'ellipsis');
  await expect(topic).toHaveAttribute('title', '/camera/<script>topic</script>');
  await page.screenshot({ path: test.info().outputPath('topics.png') });
  await page.getByRole('button', { name: 'Details', exact: true }).click();
  await expect(page.getByRole('region', { name: 'Timestamp inspection' })).toHaveCount(0);
});

test('older multi-stream artifacts use only the default front camera', async ({ page }) => {
  const api = await apiFixture(page);
  const artifact = api.recording.outputs[0].artifact!;
  artifact.streams = ['/busiest/image', '/secondary/image'].map((topic, index) => ({
    index,
    topic,
    url: artifact.url + '/streams/' + index,
    coverage_start_ns: String(index * 1000000000),
    coverage_end_ns: '4000000000',
  }));
  const media = syntheticVideo;
  api.override = async (route, path) => {
    if (!path.includes('/media/')) return false;
    await route.fulfill({ contentType: 'video/mp4', body: media });
    return true;
  };
  await page.goto('/#/analysis/42');
  await expect(page.getByRole('combobox', { name: 'Front camera stream' })).toHaveCount(0);
  const video = page.locator('.analysis-camera-front video');
  await expect(video).toHaveAttribute('src', artifact.url);
  const timeline = page.getByRole('slider', { name: 'Recording timeline', exact: true });
  await timeline.focus();
  await page.keyboard.press('ArrowRight');
  await expect(timeline).toHaveAttribute('aria-valuenow', '1');
  await expect(video).toHaveAttribute('src', artifact.url);
  await expect
    .poll(() => video.evaluate((el: HTMLVideoElement) => el.readyState))
    .toBeGreaterThanOrEqual(2);
  await page.screenshot({ path: test.info().outputPath('camera-selector.png') });
});

test('one stream needs no camera selector; missing topic inventory asks for a scan', async ({
  page,
}) => {
  await apiFixture(page);
  await page.goto('/#/analysis/42');
  await expect(page.getByRole('combobox', { name: 'Front camera stream' })).toHaveCount(0);
  await page.getByRole('button', { name: 'Topics', exact: true }).click();
  await expect(page.getByText('Rescan to load topic names.')).toBeVisible();
});

test('secondary colour streams and legacy exclusion diagnostics do not add camera controls', async ({
  page,
}) => {
  const api = await apiFixture(page);
  const artifact = api.recording.outputs[0].artifact!;
  artifact.streams = ['/robot/camera_front/color', '/other/<script>rgb</script>'].map(
    (topic, index) => ({
      index,
      topic,
      url: `${artifact.url}/streams/${index}`,
      coverage_start_ns: '1000000000',
      coverage_end_ns: '4000000000',
    }),
  );
  // Older bundles can still contain encoding-exclusion diagnostics.
  artifact.skipped_streams = ['/ouster/range_image', '/ouster/nearir_image'].map((topic) => ({
    topic,
    code: 'front_encoding_unsupported',
    message: 'Image encoding is not supported (requires rgb8 or bgr8).',
  }));
  api.override = async (route, path) => {
    if (!path.includes('/media/')) return false;
    await route.fulfill({ contentType: 'video/mp4', body: syntheticVideo });
    return true;
  };
  await page.goto('/#/analysis/42');
  await expect(page.getByRole('combobox', { name: 'Front camera stream' })).toHaveCount(0);
  await expect(page.locator('.analysis-camera-front video')).toHaveAttribute('src', artifact.url);
  await expect(page.locator('.analysis-camera-front script')).toHaveCount(0);
  await expect(page.getByRole('region', { name: 'Recording errors' })).toHaveCount(0);
  await expect(page.locator('.analysis-camera-front')).toContainText('Front');
  await page.screenshot({ path: test.info().outputPath('front-camera-default.png') });
});
