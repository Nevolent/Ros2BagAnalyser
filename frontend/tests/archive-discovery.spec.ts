import { test, expect } from '@playwright/test';
import { apiFixture } from './api-fixture';

test('page reload silently checks for new bags once, independently of polling and navigation', async ({
  page,
}) => {
  const api = await apiFixture(page);
  await page.goto('/');
  await expect.poll(() => api.discoveries.length).toBe(1);
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(3);
  await expect(page.getByText(/Checking for new recordings/)).toHaveCount(0);
  await expect(page.getByRole('button', { name: 'Rescan Archive' })).toHaveCount(0);
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await page.getByRole('link', { name: 'Recordings', exact: true }).click();
  await page.clock.install();
  await page.clock.runFor(6000);
  expect(api.discoveries).toEqual([{}]);
  expect(api.posts).toEqual([]);
  await page.reload();
  await expect.poll(() => api.discoveries.length).toBe(2);
});

test('discovery keeps existing rows and controls usable, then shows newly discovered recordings', async ({
  page,
}) => {
  const api = await apiFixture(page);
  let release!: () => void;
  const pending = new Promise<void>((resolve) => {
    release = resolve;
  });
  api.override = async (route, path) => {
    if (!path.endsWith('/discover')) return false;
    api.discoveries.push(route.request().postDataJSON());
    await pending;
    api.catalog.recordings.push({
      ...api.catalog.recordings[0],
      id: 45,
      name: 'new-recording',
      folder_path: '',
    });
    await route.fulfill({ json: { added_count: 1 } });
    return true;
  };
  await page.goto('/');
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(3);
  const selection = page.getByRole('checkbox', { name: 'Select recording-42', exact: true });
  await selection.check();
  await expect(page.getByRole('button', { name: 'Prepare Selected' })).toBeEnabled();
  await expect(page.getByText(/Checking for new recordings/)).toHaveCount(0);
  release();
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(4);
  await expect(selection).toBeChecked();
  await expect(page.getByRole('link', { name: 'new-recording', exact: true })).toBeVisible();
});

test('a failed discovery preserves the catalog and reports the failure without replaying it', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.override = async (route, path) => {
    if (!path.endsWith('/discover')) return false;
    api.discoveries.push({});
    await route.fulfill({ status: 503, json: { detail: { message: 'Archive unavailable.' } } });
    return true;
  };
  await page.goto('/');
  await expect(page.locator('.bag-table tbody tr')).toHaveCount(3);
  await expect(page.getByRole('alert')).toContainText('Archive unavailable.');
  await page.getByRole('button', { name: 'Dismiss error' }).click();
  await page.getByRole('link', { name: 'Processing', exact: true }).click();
  await page.getByRole('link', { name: 'Recordings', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveCount(0);
  expect(api.discoveries).toHaveLength(1);
});

test('settings runs a full rescan from any page and retains failures for retry', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.override = async (route, path) => {
    if (!path.endsWith('/rescan')) return false;
    api.posts.push({ path, body: route.request().postDataJSON() });
    await route.fulfill({ status: 503, json: { detail: { message: 'Full rescan failed.' } } });
    return true;
  };
  await page.goto('/#/processing');
  const settings = page.getByRole('button', { name: 'Settings', exact: true });
  await settings.click();
  const popup = page.getByRole('dialog', { name: 'Settings', exact: true });
  await popup.getByRole('button', { name: 'Do a full rescan' }).click();
  await expect(page.getByRole('alert')).toContainText('Full rescan failed.');
  await expect(popup.getByRole('button', { name: 'Do a full rescan' })).toBeEnabled();
  api.override = null;
  await popup.getByRole('button', { name: 'Do a full rescan' }).click();
  await expect(popup).toHaveCount(0);
  await expect(settings).toBeFocused();
  expect(api.posts.map((post) => post.path)).toEqual([
    '/api/v1/catalog/rescan',
    '/api/v1/catalog/rescan',
  ]);
});
