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

test('chooses a Creative Collection composition and restores its capture directions', async ({ page }) => {
  await page.goto('/multi-photo-studio');
  const collection = page.getByRole('group', { name: 'Creative Collection' });
  const choices = page.getByRole('group', { name: 'Number of photos' });
  await collection.getByRole('button', { name: 'Between Frames' }).click();
  await expect(page.locator('.multi-photo-example .multi-photo-cell')).toHaveCount(2);
  await choices.getByRole('button', { name: '3', exact: true }).click();
  await expect(page.locator('.multi-photo-example .multi-photo-cell')).toHaveCount(3);
  await page.getByLabel('Show pose prompts').uncheck();
  await page.getByRole('button', { name: 'Continue to camera' }).click();
  await expect(page.getByText('Photo 1 of 3', { exact: true })).toBeVisible();
  await expect(page.getByText('Hold a calm expression.', { exact: true })).toHaveCount(0);
  await page.getByRole('button', { name: 'Cancel session' }).click();
  await page.getByRole('link', { name: 'Multi-Photo Studio' }).click();

  await collection.getByRole('button', { name: 'Motion Study' }).click();
  const layouts = page.getByRole('group', { name: 'Layout' });
  await expect(layouts.getByRole('button', { name: 'Ascending Cut' })).toHaveAttribute('aria-pressed', 'true');
  await expect(choices.getByRole('button')).toHaveText(['4', '5', '6']);
  await choices.getByRole('button', { name: '5', exact: true }).click();
  await expect(page.getByAltText('Ascending Cut sample print with 5 photos')).toBeVisible();
  await layouts.getByRole('button', { name: 'Contact Stack' }).click();
  await expect(choices).toHaveCount(0);
  await expect(page.getByAltText('Contact Stack sample print with 4 photos')).toBeVisible();
  await layouts.getByRole('button', { name: 'Match Cut' }).click();
  const sample = page.getByAltText('Match Cut sample print with 4 photos');
  await expect(sample).toBeVisible();
  await expect.poll(() => sample.evaluate(image => (image as HTMLImageElement).naturalWidth)).toBe(720);
  await page.getByRole('button', { name: 'Continue to camera' }).click();
  await expect(page.getByText('Set your starting pose.', { exact: true })).toBeVisible();
  const saved = await page.request.get('/api/sessions/current');
  expect((await saved.json()).multi_photo_plan).toEqual({ experience: 'motion-study', layout: 'match-cut', version: 1, count: 4 });
  await page.reload();
  await expect(page.getByText('Photo 1 of 4', { exact: true })).toBeVisible();
  await expect(page.getByText('Set your starting pose.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel session' }).click();
});

test('opens Mini Scene at the first story beat and keeps a fixed-camera setup opt-in', async ({ page }) => {
  await page.goto('/multi-photo-studio');
  const collection = page.getByRole('group', { name: 'Creative Collection' });
  await expect(collection.getByRole('button', { name: 'Time Sculpture' })).toHaveCount(0);
  await collection.getByRole('button', { name: 'Mini Scene' }).click();
  await expect(page.locator('.multi-photo-example .multi-photo-cell')).toHaveCount(4);
  await page.getByRole('button', { name: 'Continue to camera' }).click();
  await expect(page.getByText('Setup · Show us who you are.', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Take first photo' })).toBeDisabled();
  await page.reload();
  await expect(page.getByText('Photo 1 of 4', { exact: true })).toBeVisible();
  await expect(page.getByText('Setup · Show us who you are.', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: 'Cancel session' }).click();
});

test('chooses a New Year template and resumes its fixed-count capture plan', async ({ page }) => {
  await page.goto('/multi-photo-studio');
  const collection = page.getByRole('group', { name: 'New Year', exact: true });
  const toggle = collection.getByRole('button', { name: 'New Year Frames' });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  const gallery = page.getByRole('group', { name: 'New Year Frames', exact: true });
  await expect(gallery.getByRole('button')).toHaveCount(13);
  const orientations = await gallery.locator('img').evaluateAll(images => images.map(image =>
    Number(image.getAttribute('width')) > Number(image.getAttribute('height'))));
  expect(orientations).toEqual([...Array(9).fill(false), ...Array(4).fill(true)]);
  for (const image of await gallery.locator('img').all()) {
    await expect.poll(() => image.evaluate(element => (element as HTMLImageElement).naturalWidth)).toBe(
      Number(await image.getAttribute('width')));
  }
  await gallery.getByRole('button', { name: 'Fresh Chapter' }).click();
  await expect(page.getByAltText('Fresh Chapter sample print with 5 photos')).toBeVisible();
  await expect(page.getByRole('group', { name: 'Number of photos' })).toHaveCount(0);
  await toggle.click();
  await expect(gallery).toHaveCount(0);
  await expect(toggle).toHaveAttribute('aria-pressed', 'true');
  await page.getByRole('button', { name: 'Continue to camera' }).click();
  await expect(page.getByText('Photo 1 of 5', { exact: true })).toBeVisible();
  const current = await page.request.get('/api/sessions/current');
  expect((await current.json()).multi_photo_plan).toEqual({ experience: 'new-year', version: 1, template: 'fresh-chapter', count: 5 });
  await page.reload();
  await expect(page.getByText('Photo 1 of 5', { exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Take 5 photos' })).toBeDisabled();
  await page.getByRole('button', { name: 'Cancel session' }).click();
});

test('chooses each added New Year design and resumes the landscape capture plan', async ({ page }) => {
  await page.goto('/multi-photo-studio');
  await page.getByRole('button', { name: 'New Year Frames', exact: true }).click();
  for (const name of ['Radiant Welcome', 'Hello 2027', 'Welcome to the Celebration', 'Champagne Cheers',
                      'New Year’s Eve', 'Glittering Welcome · Landscape', 'Burgundy Celebration',
                      'Retro Confetti', 'Aurora Celebration']) {
    await page.getByRole('button', { name: name + ' 4 photos', exact: true }).click();
    await expect(page.getByAltText(name + ' sample print with 4 photos')).toBeVisible();
  }
  const preview = page.locator('.multi-new-year-preview');
  await expect.poll(() => preview.evaluate(image => (image as HTMLImageElement).naturalWidth)).toBe(720);
  await expect(preview).toHaveAttribute('height', '480');
  await page.getByRole('button', { name: 'Continue to camera' }).click();
  await expect(page.getByText('Photo 1 of 4', { exact: true })).toBeVisible();
  await page.reload();
  await expect(page.getByText('Photo 1 of 4', { exact: true })).toBeVisible();
  const current = await page.request.get('/api/sessions/current');
  expect((await current.json()).multi_photo_plan).toEqual({ experience: 'new-year', version: 1,
    template: 'aurora-celebration', count: 4 });
  await page.getByRole('button', { name: 'Cancel session' }).click();
});
