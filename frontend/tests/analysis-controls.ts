import type { Page } from '@playwright/test';

/** Select one IMU trace using the same mode and axis controls as the user. */
export async function selectImuChannel(page: Page, channel: string) {
  const [group, axis] = channel.split('.');
  await page.getByRole('button', { name: 'Choose sensor graph', exact: true }).click();
  await page
    .getByRole('menuitemradio', {
      name: group === 'angular_velocity' ? 'Angular velocity' : 'Linear acceleration',
      exact: true,
    })
    .click();
  for (const name of ['x', 'y', 'z']) {
    const checkbox = page.getByRole('checkbox', {
      name: `${name.toUpperCase()} axis`,
      exact: true,
    });
    await checkbox.setChecked(name === axis);
  }
}
