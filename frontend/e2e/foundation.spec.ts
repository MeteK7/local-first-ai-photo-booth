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

test('configures a six-shot Signature Strip and resumes the selected plan', async ({ page }) => {
  const studio = '/multi-photo-studio';
  await page.goto('/');
  await page.getByRole('link', { name: 'Multi-Photo Studio' }).click();
  await expect(page).toHaveURL(studio);
  await page.reload();
  const choices = page.getByRole('group', { name: 'Number of photos' });
  const layouts = page.getByRole('group', { name: 'Layout' });
  const vertical = layouts.getByRole('button', { name: 'Vertical' });
  const grid = layouts.getByRole('button', { name: 'Grid' });
  await expect(choices.getByRole('button', { name: '3', exact: true })).toHaveAttribute('aria-pressed', 'true');
  await expect(vertical).toHaveAttribute('aria-pressed', 'true');
  await expect(vertical.locator('.multi-photo-cell')).toHaveCount(3);
  await choices.getByRole('button', { name: '6', exact: true }).click();
  await grid.click();
  await expect(grid).toHaveAttribute('aria-pressed', 'true');
  await expect(grid.locator('.multi-photo-cell')).toHaveCount(6);
  await page.getByRole('button', { name: 'Continue to camera' }).click();
  await expect(page.getByText('Photo 1 of 6', { exact: true })).toBeVisible();

  const session = await page.request.get('/api/sessions/current');
  expect(await session.json()).toMatchObject({
    multi_photo_plan: { experience: 'signature-strip', version: 1, layout: 'grid', count: 6 },
  });
  await page.goto(studio);
  await expect(page).toHaveURL('/session');
  await expect(page.getByRole('button', { name: 'Take 6 photos' })).toBeDisabled();
  await page.getByRole('button', { name: 'Cancel session' }).click();
  await expect(page.getByRole('link', { name: 'Multi-Photo Studio' })).toBeVisible();
});
