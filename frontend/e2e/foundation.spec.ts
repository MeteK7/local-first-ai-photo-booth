import { expect, test } from '@playwright/test';

test('can resume and finish a real database-backed booth session over loopback', async ({ page }) => {
  const external: string[] = [];
  await page.route('**/*', async route => {
    const url = new URL(route.request().url());
    if (url.hostname !== '127.0.0.1' && url.hostname !== 'localhost') {
      external.push(url.hostname);
      await route.abort();
    } else {
      await route.continue();
    }
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Single photo' }).click();
  await expect(page.getByRole('heading', { name: 'Your session' })).toBeVisible();
  await expect(page.getByText('Camera unavailable')).toBeVisible();
  await page.reload();
  await expect(page.getByRole('button', { name: 'Take photo' })).toBeDisabled();
  await page.getByRole('button', { name: 'Finish session' }).click();
  await expect(page.getByRole('button', { name: 'Single photo' })).toBeVisible();
  expect(external).toEqual([]);
});
