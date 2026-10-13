import { expect, test } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { apiFixture, detail } from './api-fixture';

test('Thumbnail mode preserves columns and selection, shows descriptions and links the entire thumbnail area to analysis', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1920, height: 1080 });
  const api = await apiFixture(page);
  api.recording.outputs.push({ kind: 'thumbnail', state: 'ready', diagnostic: null });
  api.recording.thumbnail_url = '/api/recordings/42/thumbnail/media/8';
  const png = await readFile('public/assets/front-camera-lunar-bunker.png');
  api.override = async (route, path) => {
    if (path !== api.recording.thumbnail_url) return false;
    await route.fulfill({ contentType: 'image/png', body: png });
    return true;
  };
  api.catalog.recordings = [
    api.recording,
    { ...detail(43), ai_description: { description: 'A bright outdoor scene.', bunker: false } },
  ];
  await page.goto('/');
  const row = page.locator('.bag-table tbody tr').first();
  await page.getByRole('button', { name: 'Compact', exact: true }).click();
  const before = await row.locator('td').all();
  const columns = await Promise.all(before.slice(1).map((cell) => cell.boundingBox()));
  await row.getByRole('checkbox').check();
  const thumbnail = page.getByRole('button', { name: 'Thumbnail', exact: true });
  await thumbnail.click();
  await expect(thumbnail).toHaveAttribute('aria-pressed', 'true');
  await expect(row.getByRole('checkbox')).toBeChecked();
  const controls = await Promise.all(
    [thumbnail, page.getByRole('button', { name: 'Prepare Selected', exact: true })].map((button) =>
      button.boundingBox(),
    ),
  );
  expect(controls[0]!.y + controls[0]!.height).toBeLessThan(controls[1]!.y);
  const after = await Promise.all(before.slice(1).map((cell) => cell.boundingBox()));
  columns.forEach((column, index) => expect(after[index]!.x).toBeCloseTo(column!.x, 1));
  await expect(row.locator('.recording-thumbnail img')).toBeVisible();
  await expect(row.locator('.thumbnail-loading')).toHaveCount(0);
  const description = row.locator('.recording-description');
  await expect(description).toHaveText(api.recording.ai_description!.description);
  await expect(row.getByText('Bunker', { exact: true })).toBeVisible();
  await expect(description.getByRole('button')).toHaveCount(0);
  await description.hover();
  await expect(page.getByRole('tooltip')).toHaveCount(0);
  const second = page.locator('.bag-table tbody tr').nth(1);
  await expect(second.locator('.recording-tags')).toHaveCount(0);
  const centred = await second.evaluate((element) => {
    const image = element.querySelector('.recording-thumbnail')!.getBoundingClientRect();
    const text = element.querySelector('.recording-thumbnail-copy')!.getBoundingClientRect();
    return Math.abs(image.y + image.height / 2 - text.y - text.height / 2);
  });
  expect(centred).toBeLessThan(1);
  await page.screenshot({ path: test.info().outputPath('thumbnails-desktop.png') });
  await page.setViewportSize({ width: 390, height: 1080 });
  const trigger = description.locator('.recording-description-trigger');
  await expect(trigger).toBeVisible();
  await trigger.hover();
  const tooltip = page.getByRole('tooltip');
  await expect(tooltip).toHaveText(api.recording.ai_description!.description);
  await expect(trigger).toHaveAttribute('aria-describedby', (await tooltip.getAttribute('id'))!);
  await page.keyboard.press('Escape');
  await expect(tooltip).toHaveCount(0);
  await page.setViewportSize({ width: 1920, height: 1080 });
  await expect(trigger).toHaveCount(0);
  await description.hover();
  await expect(tooltip).toHaveCount(0);
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await page.getByRole('link', { name: 'Recordings', exact: true }).click();
  await expect(thumbnail).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Compact', exact: true }).click();
  await expect(page.locator('.recording-thumbnail')).toHaveCount(0);
  await expect(row.getByRole('checkbox')).toBeChecked();
});

test('Thumbnail placeholders truthfully track queued, processing, missing, failed and load failure', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.catalog.recordings = [
    'not_requested',
    'queued',
    'processing',
    'failed',
    'ready',
    'unavailable',
  ].map((state, index) => ({
    ...detail(42 + index),
    thumbnail_url: state === 'ready' ? '/api/recordings/46/thumbnail/media/9' : null,
    outputs: [
      {
        kind: 'thumbnail',
        state,
        diagnostic:
          state === 'failed'
            ? { code: 'thumbnail_processing_failed', message: 'Synthetic thumbnail failure.' }
            : state === 'unavailable'
              ? {
                  code: 'thumbnail_camera_unavailable',
                  message: 'No supported colour camera is available for a thumbnail.',
                }
              : null,
      },
    ],
  }));
  api.override = async (route, path) => {
    if (!path.includes('/thumbnail/media/')) return false;
    await route.fulfill({ status: 404 });
    return true;
  };
  await page.goto('/');
  await page.getByRole('button', { name: 'Thumbnail', exact: true }).click();
  const placeholders = page.locator('.recording-thumbnail');
  await expect(placeholders).toHaveText([
    'No Thumbnail',
    'Queued',
    'Processing',
    'No Thumbnail',
    'No Thumbnail',
    'No Thumbnail',
  ]);
  const tooltip = page.getByRole('tooltip');
  const mutedColor = await placeholders
    .first()
    .evaluate((element) => getComputedStyle(element).color);
  for (const index of [3, 4, 5]) {
    const placeholder = placeholders.nth(index);
    await expect(placeholder.locator('span')).toHaveCSS('color', mutedColor);
    await placeholder.hover();
    await expect(tooltip).toHaveCount(0);
    await placeholder.locator('..').focus();
    await expect(tooltip).toHaveCount(0);
  }
  await page.setViewportSize({ width: 390, height: 1000 });
  await placeholders.nth(5).hover();
  await expect(placeholders.nth(5).locator('span')).toHaveCSS('color', mutedColor);
  await expect(tooltip).toHaveCount(0);
});

for (const state of ['failed', 'unavailable'] as const) {
  test(`thumbnail ${state} diagnostics appear safely in Analysis with a muted list placeholder`, async ({
    page,
  }) => {
    const api = await apiFixture(page);
    const message = 'Thumbnail: <script>not markup</script> No usable image could be decoded.';
    api.recording.outputs.push({
      kind: 'thumbnail',
      state,
      diagnostic: { code: 'thumbnail_processing_failed', message },
    });
    api.catalog.recordings = [api.recording];
    await page.goto('/');
    const thumbnail = page.locator('.recording-thumbnail');
    await expect(thumbnail).toHaveText('No Thumbnail');
    await expect(thumbnail.locator('.status-error')).toHaveCount(0);
    await thumbnail.hover();
    await expect(page.getByRole('tooltip')).toHaveCount(0);
    await thumbnail.click();
    await expect(page).toHaveURL(/#\/analysis\/42$/);
    const errors = page.getByRole('region', { name: 'Recording errors' });
    await expect(errors).toContainText(message);
    await expect(errors.locator('script')).toHaveCount(0);
  });
}

for (const width of [1440, 390]) {
  test(`long AI text is safely truncated and row controls stay usable at ${width}px`, async ({
    page,
  }) => {
    await page.setViewportSize({ width, height: 1000 });
    const api = await apiFixture(page);
    const description =
      'A camera scene. <img src=x onerror=alert(1)> ' +
      'A visible scene with terrain, props and artificial lighting '.repeat(10) +
      '.';
    api.recording.ai_description = { description, bunker: false };
    api.catalog.recordings = [api.recording];
    await page.goto('/');
    await page.getByRole('button', { name: 'Thumbnail', exact: true }).click();
    const row = page.locator('.bag-table tbody tr');
    const text = row.locator('.recording-description-trigger');
    await expect(text).toBeVisible();
    await expect(text).toHaveText(description);
    await expect(text).toHaveCSS('text-overflow', 'ellipsis');
    await expect(text.locator('img')).toHaveCount(0);
    expect(await text.evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
    await page.keyboard.press('Tab');
    await row.locator('.recording-thumbnail-row').focus();
    await expect(page.getByRole('tooltip')).toHaveText(description);
    await page.keyboard.press('Escape');
    await row.getByRole('checkbox').check();
    await page.getByRole('button', { name: 'Prepare Selected', exact: true }).click();
    await expect(page.getByRole('dialog')).toContainText('thumbnails');
    await page.getByRole('button', { name: 'Cancel', exact: true }).click();
    await page.screenshot({ path: test.info().outputPath(`thumbnails-${width}.png`) });
  });
}

test('catalog rejects a thumbnail URL outside its recording and API route', async ({ page }) => {
  const api = await apiFixture(page);
  api.recording.thumbnail_url = 'https://example.com/untrusted.png';
  await page.goto('/');
  await expect(page.getByText('Invalid thumbnail URL.')).toBeVisible();
  await expect(page.locator('.recording-thumbnail img')).toHaveCount(0);
});

for (const area of [
  '.recording-thumbnail',
  '.bag-name',
  '.recording-description',
  '.recording-tags',
  '.recording-thumbnail-copy',
]) {
  test(`thumbnail area ${area} opens analysis`, async ({ page }) => {
    const api = await apiFixture(page);
    api.catalog.recordings = [api.recording];
    await page.goto('/');
    await page.getByRole('button', { name: 'Thumbnail', exact: true }).click();
    const target = page.locator('.bag-table tbody tr').first().locator(area);
    if (area === '.recording-thumbnail-copy') {
      const gap = await target.evaluate((element) => {
        const title = element.querySelector('.bag-name')!.getBoundingClientRect();
        const description = element
          .querySelector('.recording-description')!
          .getBoundingClientRect();
        return { x: title.left + 4, y: (title.bottom + description.top) / 2 };
      });
      await page.mouse.click(gap.x, gap.y);
    } else await target.click();
    await expect(page).toHaveURL(/#\/analysis\/42$/);
  });
}

test('thumbnail navigation supports keyboard activation', async ({ page }) => {
  const api = await apiFixture(page);
  api.catalog.recordings = [api.recording];
  await page.goto('/');
  await page.getByRole('button', { name: 'Thumbnail', exact: true }).click();
  const link = page.getByRole('link', { name: `Analyze ${api.recording.name}` });
  await link.focus();
  await link.press('Enter');
  await expect(page).toHaveURL(/#\/analysis\/42$/);
});

test('hovering any row cell immediately advances the thumbnail and cycles every 750 ms', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.recording.outputs.push({ kind: 'thumbnail', state: 'ready', diagnostic: null });
  api.recording.thumbnail_url = '/api/recordings/42/thumbnail/media/8';
  api.recording.thumbnail_frame_count = 6;
  api.catalog.recordings = [api.recording];
  const png = await readFile('public/assets/front-camera-lunar-bunker.png');
  api.override = async (route, path) => {
    if (path !== api.recording.thumbnail_url) return false;
    await route.fulfill({ contentType: 'image/png', body: png });
    return true;
  };
  await page.clock.install();
  await page.goto('/');
  const row = page.locator('.bag-table tbody tr');
  const thumbnail = row.locator('.recording-thumbnail');
  await expect(row.locator('.thumbnail-loading')).toHaveCount(0);
  await expect(thumbnail).toHaveAttribute('data-thumbnail-frame', '3');
  await row.locator('td').nth(2).hover();
  await expect(thumbnail).toHaveAttribute('data-thumbnail-frame', '4');
  await page.clock.runFor(700);
  await expect(thumbnail).toHaveAttribute('data-thumbnail-frame', '4');
  await page.clock.runFor(60);
  await expect(thumbnail).toHaveAttribute('data-thumbnail-frame', '5');
  await page.getByRole('heading', { name: 'Recordings', exact: true }).hover();
  await expect(thumbnail).toHaveAttribute('data-thumbnail-frame', '3');
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await row.locator('td').nth(2).hover();
  await page.clock.runFor(1600);
  await expect(thumbnail).toHaveAttribute('data-thumbnail-frame', '3');
});

test('phone touch input keeps the thumbnail still', async ({ browser }) => {
  const context = await browser.newContext({
    baseURL: test.info().project.use.baseURL,
    viewport: { width: 390, height: 900 },
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  const api = await apiFixture(page);
  api.recording.outputs.push({ kind: 'thumbnail', state: 'ready', diagnostic: null });
  api.recording.thumbnail_url = '/api/recordings/42/thumbnail/media/8';
  api.recording.thumbnail_frame_count = 6;
  api.catalog.recordings = [api.recording];
  const png = await readFile('public/assets/front-camera-lunar-bunker.png');
  api.override = async (route, path) => {
    if (path !== api.recording.thumbnail_url) return false;
    await route.fulfill({ contentType: 'image/png', body: png });
    return true;
  };
  await page.clock.install();
  await page.goto('/');
  const thumbnail = page.locator('.recording-thumbnail');
  await thumbnail.hover();
  await page.clock.runFor(1500);
  await expect(thumbnail).toHaveAttribute('data-thumbnail-frame', '3');
  await context.close();
});
