import { test, expect, type Page } from '@playwright/test';
import { apiFixture, job } from './api-fixture';

function deferred() {
  let resolve!: () => void;
  const promise = new Promise<void>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

async function prepare(page: Page, goToProcessing = true) {
  await page.getByRole('checkbox', { name: 'Select recording-42', exact: true }).check();
  await page.getByRole('button', { name: 'Prepare Selected' }).click();
  const dialog = page.getByRole('dialog', { name: 'Prepare recordings' });
  await dialog.getByRole('checkbox', { name: 'Go to Processing' }).setChecked(goToProcessing);
  await dialog.getByRole('button', { name: 'Confirm', exact: true }).click();
  await expect(dialog).toBeHidden();
}

for (const cachedRows of [0, 1]) {
  test(`preparation keeps an empty queue loading and preserves ${cachedRows} cached rows through its refresh`, async ({
    page,
  }) => {
    const api = await apiFixture(page);
    api.active = null;
    api.failures = [];
    api.queue = cachedRows ? [{ ...job(90), recording_name: 'existing-recording' }] : [];
    const preparation = deferred();
    const queueRead = deferred();
    const refreshStarted = deferred();
    let accepted = false;
    api.override = async (route, path) => {
      if (path.endsWith('/prepare')) {
        await preparation.promise;
        api.queue.push({ ...job(99), recording_id: 42 });
        accepted = true;
        await route.fulfill({ status: 202, json: { items: [{ outcome: 'queued' }] } });
        return true;
      }
      if (
        accepted &&
        path === '/api/v1/processing/jobs' &&
        new URL(route.request().url()).searchParams.get('view') === 'queued'
      ) {
        refreshStarted.resolve();
        await queueRead.promise;
      }
      return false;
    };
    try {
      await page.goto('/#/processing');
      const rows = page.locator('.processing-queue-table tbody tr');
      await expect(rows).toHaveCount(cachedRows);
      if (!cachedRows)
        await expect(page.getByText('No queued jobs.', { exact: true })).toBeVisible();
      else await expect(rows).toContainText('existing-recording');
      await page.getByRole('link', { name: 'Recordings', exact: true }).click();
      await prepare(page);
      await expect(page).toHaveURL(/#\/processing$/);
      const loading = page.getByText('Loading queue…', { exact: true });
      if (!cachedRows) {
        await expect(loading).toBeVisible();
        await page
          .locator('[data-processing-table]')
          .screenshot({ path: test.info().outputPath('pending-queue.png') });
      } else {
        await expect(loading).toBeHidden();
        await expect(rows).toContainText('existing-recording');
      }
      await expect(page.getByText('No queued jobs.', { exact: true })).toBeHidden();
      await expect(
        page.getByRole('button', { name: 'Queue', exact: true }).locator('.page-tab-count'),
      ).toHaveText(String(cachedRows));
      preparation.resolve();
      await refreshStarted.promise;
      await expect(rows).toHaveCount(cachedRows);
      if (!cachedRows) await expect(loading).toBeVisible();
      queueRead.resolve();
      await expect(rows).toHaveCount(cachedRows + 1);
      await expect(rows.filter({ hasText: 'recording-42' })).toBeVisible();
      await expect(loading).toBeHidden();
    } finally {
      preparation.resolve();
      queueRead.resolve();
    }
  });
}

test('preparation completed on Recordings invalidates a previously empty Processing queue', async ({
  page,
}) => {
  const api = await apiFixture(page);
  api.active = null;
  api.queue = [];
  api.failures = [];
  const queueRead = deferred();
  let accepted = false;
  api.override = async (route, path) => {
    if (path.endsWith('/prepare')) {
      api.queue = [{ ...job(99), recording_id: 42 }];
      accepted = true;
      await route.fulfill({ status: 202, json: { items: [{ outcome: 'queued' }] } });
      return true;
    }
    if (
      accepted &&
      path === '/api/v1/processing/jobs' &&
      new URL(route.request().url()).searchParams.get('view') === 'queued'
    )
      await queueRead.promise;
    return false;
  };
  try {
    await page.goto('/#/processing');
    await expect(page.getByText('No queued jobs.', { exact: true })).toBeVisible();
    await page.getByRole('link', { name: 'Recordings', exact: true }).click();
    await prepare(page, false);
    await expect(
      page.getByRole('status').filter({ hasText: 'Preparation request completed.' }),
    ).toBeVisible();
    await page.getByRole('link', { name: 'Processing', exact: true }).click();
    await expect(page.getByText('Loading queue…', { exact: true })).toBeVisible();
    await expect(page.getByText('No queued jobs.', { exact: true })).toBeHidden();
    queueRead.resolve();
    await expect(page.locator('.processing-queue-table tbody')).toContainText('recording-42');
    await expect(page.getByText('Loading queue…', { exact: true })).toBeHidden();
  } finally {
    queueRead.resolve();
  }
});

for (const outcome of ['ready_reused', 'request_failed']) {
  test(`${outcome} clears pending queue loading without inventing queued jobs`, async ({
    page,
  }) => {
    const api = await apiFixture(page);
    api.active = null;
    api.queue = [];
    api.failures = [];
    const preparation = deferred();
    api.override = async (route, path) => {
      if (!path.endsWith('/prepare')) return false;
      await preparation.promise;
      await route.fulfill(
        outcome === 'ready_reused'
          ? { json: { items: [{ outcome }] } }
          : { status: 503, json: { detail: { message: 'Worker storage unavailable.' } } },
      );
      return true;
    };
    try {
      await page.goto('/#/processing');
      await expect(page.getByText('No queued jobs.', { exact: true })).toBeVisible();
      await page.getByRole('link', { name: 'Recordings', exact: true }).click();
      await prepare(page);
      await expect(page.getByText('Loading queue…', { exact: true })).toBeVisible();
      preparation.resolve();
      if (outcome === 'request_failed') {
        await expect(page.getByRole('alert')).toHaveText('Worker storage unavailable.');
        await page.getByRole('button', { name: 'Dismiss error' }).click();
      }
      await expect(page.getByText('No queued jobs.', { exact: true })).toBeVisible();
      await expect(page.getByText('Loading queue…', { exact: true })).toBeHidden();
      await expect(page.locator('.processing-queue-table tbody tr')).toHaveCount(0);
    } finally {
      preparation.resolve();
    }
  });
}
