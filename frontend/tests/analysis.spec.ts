import { test, expect } from '@playwright/test';

test('timeline plays, pauses and scrubs', async ({ page }) => {
  await page.goto('/?demo=1#/analysis');
  await page.clock.install();
  const slider = page.getByRole('slider', { name: 'Recording timeline' });
  const value = page.locator('[data-timeline-value]');
  const originalValue = await value.textContent();
  const originalCursor = await page.locator('.timeline-cursor').getAttribute('transform');
  await expect(page.locator('.timeline-cursor circle')).toHaveCount(1);
  await page.getByRole('button', { name: 'Play timeline', exact: true }).click();
  await expect(page.locator('.timeline-cursor circle')).toHaveCount(0);
  await page.clock.runFor(2100);
  expect(Number(await slider.getAttribute('aria-valuenow'))).toBeGreaterThan(2);
  expect(await value.textContent()).not.toBe(originalValue);
  expect(await page.locator('.timeline-cursor').getAttribute('transform')).not.toBe(originalCursor);
  await page.getByRole('button', { name: 'Pause timeline', exact: true }).click();
  await expect(page.locator('.timeline-cursor circle')).toHaveCount(1);
  const paused = await slider.getAttribute('aria-valuenow');
  await page.clock.runFor(1000);
  await expect(slider).toHaveAttribute('aria-valuenow', paused!);
  const bounds = (await slider.boundingBox())!;
  await page.mouse.move(bounds.x + bounds.width * 0.25, bounds.y + 80);
  await page.mouse.down();
  await page.mouse.move(bounds.x + bounds.width * 0.6, bounds.y + 80);
  await page.mouse.up();
  expect(Number(await slider.getAttribute('aria-valuenow'))).toBeCloseTo(754.56 * 0.6, 0);
  await expect(page.locator('[data-camera-time]')).toHaveCount(0);
  await expect(page.locator('.chart-tooltip')).toHaveCount(0);
});

test('channel menu, zoom and help work with mouse and keyboard', async ({ page }) => {
  await page.goto('/?demo=1#/analysis');
  const slider = page.getByRole('slider', { name: 'Recording timeline' });
  await slider.press('Home');
  await slider.press('Shift+ArrowRight');
  await expect(slider).toHaveAttribute('aria-valuenow', '10');
  const currentTime = await slider.getAttribute('aria-valuenow');
  const initialPath = await page.locator('.timeline-line').getAttribute('d');
  const channel = page.getByRole('button', { name: 'Choose sensor graph' });
  await channel.click();
  await page.getByRole('menuitemradio', { name: 'angular_velocity.x', exact: true }).click();
  await expect(page.locator('[data-channel-label]')).toHaveText('angular_velocity.x');
  await expect(slider).toHaveAttribute('aria-valuenow', currentTime!);
  expect(await page.locator('.timeline-line').getAttribute('d')).not.toBe(initialPath);
  await expect(page.locator('.timeline-grid text')).toHaveText(['2', '1', '0', '-1', '-2']);
  await channel.press('ArrowDown');
  await page.keyboard.press('ArrowDown');
  await page.keyboard.press('Enter');
  await expect(page.locator('[data-channel-label]')).toHaveText('angular_velocity.y');
  await expect(channel).toBeFocused();
  await channel.click();
  await channel.click();
  await expect(page.getByRole('menu', { name: 'Sensor channel' })).toBeHidden();
  await channel.click();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('menu', { name: 'Sensor channel' })).toBeHidden();
  const range = page.locator('[data-timeline-end]');
  const end = await range.textContent();
  await page.getByRole('button', { name: 'Zoom in', exact: true }).click();
  expect(Number(await range.textContent())).toBeLessThan(Number(end));
  await page.getByRole('button', { name: 'Reset zoom', exact: true }).click();
  await expect(range).toHaveText(end!);
  await expect(slider).toHaveAttribute('aria-valuenow', currentTime!);
  await page.getByRole('button', { name: 'Graph help' }).click();
  await expect(page.getByRole('region', { name: 'Timeline controls' })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(page.getByRole('region', { name: 'Timeline controls' })).toBeHidden();
});

test('playback stops at the end, can restart, and is disposed when leaving Analysis', async ({
  page,
}) => {
  await page.goto('/?demo=1#/analysis');
  await page.clock.install();
  const slider = page.getByRole('slider', { name: 'Recording timeline' });
  await slider.press('End');
  await expect(slider).toHaveAttribute('aria-valuenow', '754.56');
  await slider.press('ArrowLeft');
  await slider.press('Space');
  await page.clock.runFor(1200);
  await expect(slider).toHaveAttribute('aria-valuenow', '754.56');
  await expect(page.getByRole('button', { name: 'Play timeline', exact: true })).toBeVisible();
  await slider.press('Space');
  await page.clock.runFor(500);
  expect(Number(await slider.getAttribute('aria-valuenow'))).toBeLessThan(1);
  await page.evaluate(() => {
    (window as any).previousTimeline = document.querySelector('[data-timeline-plot]');
  });
  await page.getByRole('link', { name: 'Recordings', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'Recordings', exact: true, level: 1 }),
  ).toBeVisible();
  const oldTime = await page.evaluate(() =>
    (window as any).previousTimeline.getAttribute('aria-valuenow'),
  );
  await page.clock.runFor(2000);
  expect(
    await page.evaluate(() => (window as any).previousTimeline.getAttribute('aria-valuenow')),
  ).toBe(oldTime);
  await page.getByRole('link', { name: 'Analysis', exact: true }).click();
  await expect(slider).toHaveAttribute('aria-valuenow', '0');
});

test('sidebar labels appear to the right on hover and keyboard focus', async ({ page }) => {
  await page.goto('/?demo=1');
  for (const [name, label] of [
    ['Tectrace home', 'Tectrace'],
    ['Recordings', 'Recordings'],
    ['Analysis', 'Analysis'],
    ['Processing', 'Processing'],
  ]) {
    const link = page.getByRole('link', { name, exact: true });
    await link.hover();
    const tooltip = page.getByRole('tooltip');
    await expect(tooltip).toHaveText(label);
    const anchor = (await link.boundingBox())!;
    const bubble = (await tooltip.boundingBox())!;
    expect(bubble.x).toBeGreaterThan(anchor.x + anchor.width);
    expect(Math.abs(bubble.y + bubble.height / 2 - anchor.y - anchor.height / 2)).toBeLessThan(1);
    await page.keyboard.press('Escape');
    await expect(tooltip).toHaveCount(0);
  }
  await page.getByRole('link', { name: 'Tectrace home' }).focus();
  await expect(page.getByRole('tooltip')).toHaveText('Tectrace');
  await expect(page.locator('[data-rail-link][aria-label="Analysis"] svg')).toHaveClass(
    /chart-column/,
  );
  await expect(page.locator('[data-rail-link][aria-label="Processing"] svg')).toHaveClass(
    /git-branch/,
  );
});

test('sidebar tooltip stays visible while crossing between Recordings and the logo', async ({
  page,
}) => {
  await page.clock.install();
  await page.goto('/?demo=1');
  const recordings = page.getByRole('link', { name: 'Recordings', exact: true });
  const logo = page.getByRole('link', { name: 'Tectrace home' });
  const tooltip = page.getByRole('tooltip');

  await recordings.hover();
  await page.clock.runFor(40);
  await expect(tooltip).toHaveText('Recordings');
  await tooltip.evaluate((element) => element.setAttribute('data-reuse-check', 'original'));

  const recordingBox = (await recordings.boundingBox())!;
  await page.mouse.move(recordingBox.x + recordingBox.width / 2, recordingBox.y - 5);
  await page.clock.runFor(120);
  await expect(tooltip).not.toHaveClass(/is-leaving/);
  await logo.hover();
  await expect(tooltip).toHaveText('Tectrace');
  await expect(tooltip).toHaveAttribute('data-reuse-check', 'original');

  const logoBox = (await logo.boundingBox())!;
  await page.mouse.move(logoBox.x + logoBox.width / 2, logoBox.y + logoBox.height + 5);
  await page.clock.runFor(120);
  await expect(tooltip).not.toHaveClass(/is-leaving/);
  await recordings.hover();
  await expect(tooltip).toHaveText('Recordings');
  await expect(tooltip).toHaveAttribute('data-reuse-check', 'original');
});

test('recording details retain asset metadata and scroll with a reserved gutter', async ({
  page,
}) => {
  await page.setViewportSize({ width: 1024, height: 500 });
  await page.goto('/?demo=1#/analysis');
  const body = page.getByRole('region', { name: 'Recording information and assets' });
  await expect(page.getByRole('heading', { name: 'Recording info', exact: true })).toHaveCount(0);
  await expect(body).not.toContainText('bunker_testing_2025-12-30_10-25-00.bag');
  await expect(page.locator('.analysis-recording-name')).toHaveText(
    'bunker_testing_2025-12-30_10-25-00.bag',
  );
  await expect(body).toContainText('2,486');
  await expect(body).toContainText('4.82 GB');
  await expect(body).toContainText('metadata.yaml');
  await expect(body.getByRole('heading', { name: 'Analysis outputs' })).toHaveCount(0);
  await expect(body.getByRole('heading', { name: 'Source components' })).toHaveCount(0);
  await expect(body).toHaveCSS('scrollbar-gutter', 'stable');
  const before = await body.boundingBox();
  await page.addStyleTag({ content: '.recording-details-body { overflow-y:scroll; }' });
  expect(await body.boundingBox()).toEqual(before);
  expect(await body.evaluate((el) => el.scrollHeight > el.clientHeight)).toBe(true);
  await body.focus();
  await page.keyboard.press('Control+End');
  await body.evaluate((el) => {
    el.scrollTop = el.scrollHeight;
  });
  await expect(body.getByText('data_0.db3', { exact: true })).toBeInViewport();
  await expect(
    page.getByRole('heading', { name: 'Recording details', exact: true }),
  ).toBeInViewport();
  await page.getByRole('button', { name: 'Collapse recording details' }).click();
  await expect(page.getByRole('button', { name: 'Expand recording details' })).toBeFocused();
  await page.getByRole('button', { name: 'Expand recording details' }).click();
  await expect(body).toBeVisible();
});

for (const width of [390, 640, 768, 1024, 1440, 1920]) {
  test(`pages share their outer bounds and Analysis stays usable at ${width}px`, async ({
    page,
  }) => {
    const errors: string[] = [];
    page.on('pageerror', (e) => errors.push(e.message));
    await page.setViewportSize({ width, height: 844 });
    await page.goto('/?demo=1');
    const recordings = (await page.locator('.dashboard-workspace').boundingBox())!;
    const folders = (await page.locator('.folder-card').boundingBox())!;
    await page.getByRole('link', { name: 'Analysis', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: 'Analysis', exact: true, level: 1 }),
    ).toBeVisible();
    const analysis = (await page.locator('.dashboard-workspace').boundingBox())!;
    expect(analysis).toEqual(recordings);
    if (width > 600) {
      const details = (await page.locator('.folder-card').boundingBox())!;
      expect(details.width).toBeGreaterThanOrEqual(280);
      expect(details.y).toBe(folders.y);
      expect(details.y + details.height).toBe(folders.y + folders.height);
      const front = (await page.locator('.analysis-camera-front').boundingBox())!;
      const top = (await page.locator('.analysis-camera-top').boundingBox())!;
      const graph = (await page.locator('.analysis-timeline').boundingBox())!;
      expect(top.x - front.x - front.width).toBeCloseTo(8, 1);
      expect(top.x + top.width).toBeCloseTo(graph.x + graph.width, 1);
    }
    const slider = page.getByRole('slider', { name: 'Recording timeline' });
    await slider.scrollIntoViewIfNeeded();
    await slider.press('ArrowRight');
    await expect(slider).toHaveAttribute('aria-valuenow', '1');
    const axis = page.locator('.timeline-axis');
    const labels = await axis.locator('time').all();
    const start = (await labels[0].boundingBox())!,
      end = (await labels[1].boundingBox())!;
    const plot = (await slider.boundingBox())!;
    expect(start.y).toBe(end.y);
    expect(start.x).toBeCloseTo(plot.x + 6, 1);
    expect(end.x).toBeGreaterThan(start.x + start.width);
    expect(end.x + end.width).toBeCloseTo(plot.x + plot.width - 6, 1);
    await expect(axis).toHaveCSS('justify-content', 'space-between');
    await expect(axis).toHaveCSS('font-size', '11.5px');
    const colors = await axis
      .locator('time')
      .evaluateAll((items) => items.map((item) => getComputedStyle(item).color));
    expect(colors[0]).not.toBe(colors[1]);
    expect(
      await page.evaluate(
        () =>
          document.documentElement.scrollWidth <= innerWidth &&
          document.documentElement.scrollHeight <= innerHeight,
      ),
    ).toBe(true);
    await page.getByRole('heading', { name: 'Analysis', exact: true, level: 1 }).click();
    if ([390, 1440, 1920].includes(width))
      await page.screenshot({ path: test.info().outputPath(`analysis-${width}.png`) });
    await page.getByRole('link', { name: 'Processing', exact: true }).click();
    await expect(
      page.getByRole('heading', { name: 'Processing', exact: true, level: 1 }),
    ).toBeVisible();
    expect(await page.locator('.dashboard-workspace').boundingBox()).toEqual(recordings);
    expect(errors).toEqual([]);
  });
}

test('sidebar labels are readable, appear quickly and reuse one label between icons', async ({
  page,
}) => {
  await page.clock.install();
  await page.goto('/?demo=1');
  await page.getByRole('link', { name: 'Recordings', exact: true }).hover();
  await page.clock.runFor(40);
  const tooltip = page.getByRole('tooltip');
  await expect(tooltip).toHaveText('Recordings');
  // The existing design is 18px line-height + 4px padding per side.
  // offsetHeight excludes the entrance animation's temporary scale.
  const compactHeight = await tooltip.evaluate((el) => (el as HTMLElement).offsetHeight);
  expect(compactHeight).toBe(26);
  await tooltip.evaluate((el) => {
    el.setAttribute('data-reuse-check', 'original');
  });
  await page.getByRole('link', { name: 'Analysis', exact: true }).hover();
  await expect(tooltip).toHaveText('Analysis');
  await expect(tooltip).toHaveAttribute('data-reuse-check', 'original');
  await expect(tooltip).not.toHaveClass(/is-leaving/);
  const arrow = await tooltip.evaluate((el) => {
    const style = getComputedStyle(el, '::before');
    return { content: style.content, width: style.width, transform: style.transform };
  });
  expect(arrow.content).not.toBe('none');
  expect(arrow.width).toBe('6px');
  expect(arrow.transform).not.toBe('none');
  await page.mouse.move(300, 300);
  await expect(tooltip).not.toHaveClass(/is-leaving/);
  await page.clock.runFor(70);
  await expect(tooltip).toHaveClass(/is-leaving/);
  await page.clock.runFor(160);
  await expect(tooltip).toHaveCount(0);
  await page.getByRole('link', { name: 'Processing', exact: true }).hover();
  await page.clock.runFor(40);
  await expect(page.getByRole('tooltip')).toHaveText('Processing');
  await page.keyboard.press('Escape');
  await expect(tooltip).toHaveCount(0);
});
