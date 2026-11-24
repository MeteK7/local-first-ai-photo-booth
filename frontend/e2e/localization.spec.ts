import { expect, test } from '@playwright/test';

test('switches the live kiosk in place and keeps admin and customer preferences separate', async ({ page }) => {
  const external: string[] = [];
  await page.route('**/*', async route => {
    const { hostname } = new URL(route.request().url());
    if (hostname !== '127.0.0.1' && hostname !== 'localhost') {
      external.push(route.request().url());
      await route.abort();
    } else {
      await route.continue();
    }
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Single photo' }).click();
  await expect(page.getByText('Camera unavailable', { exact: true })).toBeVisible();
  const initial = await page.request.get('/api/sessions/current').then(response => response.json());
  const requests: string[] = [];
  const track = (request: { url(): string }) => requests.push(request.url());
  page.on('request', track);
  await page.getByRole('button', { name: 'Türkçe' }).click();
  await expect(page.locator('html')).toHaveAttribute('lang', 'tr');
  await expect(page.getByRole('heading', { name: 'Oturumunuz' })).toBeVisible();
  await expect(page.getByText('Kamera kullanılamıyor', { exact: true })).toBeVisible();
  // The session already polls its local camera. A switch needs only those existing requests.
  expect(requests.every(url => new URL(url).pathname === '/api/camera/status')).toBe(true);
  page.off('request', track);
  const current = await page.request.get('/api/sessions/current').then(response => response.json());
  expect(current.id).toBe(initial.id);

  await page.reload();
  await expect(page.getByRole('heading', { name: 'Oturumunuz' })).toBeVisible();
  await page.getByRole('button', { name: 'Oturumu bitir' }).click();
  await expect(page.getByRole('button', { name: 'Tek fotoğraf' })).toBeVisible();
  await page.setViewportSize({ width: 360, height: 800 });
  await expect(page.getByRole('button', { name: 'Türkçe' })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
  await page.getByRole('link', { name: 'Yönetim' }).click();
  await expect(page.getByLabel('Username')).toBeVisible();
  await page.getByLabel('Username').fill('localization-invalid-fixture');
  await page.getByLabel('Password').fill('invalid-fixture-password');
  await page.getByRole('button', { name: 'Sign in', exact: true }).click();
  await expect(page.getByRole('alert')).toHaveText('The username or password is incorrect.');
  await page.getByRole('button', { name: 'Türkçe' }).click();
  await expect(page.getByLabel('Kullanıcı adı')).toBeVisible();
  await expect(page.getByRole('alert')).toHaveText('Kullanıcı adı veya parola yanlış.');
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(360);
  await page.reload();
  await expect(page.getByLabel('Kullanıcı adı')).toBeVisible();
  await page.getByRole('button', { name: 'English' }).click();
  await expect(page.getByLabel('Username')).toBeVisible();
  await page.getByRole('link', { name: 'LOCAL PHOTO BOOTH' }).click();
  await expect(page.getByRole('button', { name: 'Tek fotoğraf' })).toBeVisible();
  await page.getByRole('button', { name: 'Tek fotoğraf' }).click();
  await page.getByRole('button', { name: 'Oturumu iptal et' }).click();
  await expect(page.getByRole('button', { name: 'Tek fotoğraf' })).toBeVisible();
  expect(external).toEqual([]);
});

test('translates a queued treatment without changing the selection or resubmitting', async ({ page }) => {
  const photos = '/api/sessions/current/photos';
  const source = { id: 'localization-source', width: 6000, height: 4000, byte_size: 100, captured_at: '2026-11-20T08:00:00Z' };
  const job = { id: 'queued-treatment', kind: 'creative', state: 'queued', detail: 'Waiting to prepare your photo.',
    messages: [{ key: 'messages.creative.queued' }] };
  let submissions = 0;
  await page.route(url => url.pathname === photos + '/latest', route => route.fulfill({ json: source }));
  await page.route(url => url.pathname === photos + '/print-jobs', route => route.fulfill({ json: null }));
  await page.route(url => url.pathname === photos + '/creative', route => {
    if (route.request().method() === 'POST') {
      submissions++;
      return route.fulfill({ status: 202, json: job });
    }
    return route.fulfill({ json: [{
      id: 'film-frame', name: 'The Film Frame', description: 'Film grain and a matte.', result: submissions ? job : null,
    }] });
  });

  await page.goto('/');
  await page.getByRole('button', { name: 'Single photo' }).click();
  await page.getByRole('button', { name: 'The Film Frame', exact: true }).click();
  await expect(page.getByText(job.detail)).toBeVisible();
  await page.getByRole('button', { name: 'Türkçe' }).click();
  await expect(page.getByText('Fotoğrafınız hazırlanmak üzere sırada.')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Film Karesi', exact: true })).toHaveAttribute('aria-pressed', 'true');
  expect(submissions).toBe(1);
  await page.getByRole('button', { name: 'Oturumu bitir' }).click();
  await expect(page.getByRole('button', { name: 'Tek fotoğraf' })).toBeVisible();
});

test('captures a D5600 photo and renders a Turkish Film Frame', async ({ page, baseURL }) => {
  test.skip(process.env['PHOTOBOOTH_I18N_HARDWARE_TEST'] !== '1', 'This test fires a real shutter.');
  test.setTimeout(75_000);
  const photos = '/api/sessions/current/photos';
  try {
    await page.goto('/');
    await page.getByRole('button', { name: 'Türkçe' }).click();
    await page.getByRole('button', { name: 'Tek fotoğraf' }).click();
    const shutter = page.getByRole('button', { name: 'Fotoğraf çek', exact: true });
    await expect(shutter).toBeEnabled({ timeout: 15_000 });
    const pendingCapture = page.waitForResponse(response =>
      new URL(response.url()).pathname === photos && response.request().method() === 'POST',
    );
    await shutter.click();
    await expect(page.locator('.countdown')).toHaveText('3');
    await page.getByRole('button', { name: 'English' }).click();
    await expect(page.getByRole('heading', { name: 'Your session' })).toBeVisible();
    await page.getByRole('button', { name: 'Türkçe' }).click();
    const capture = await pendingCapture;
    expect(capture.status(), await capture.text()).toBe(201);
    expect(await capture.json()).toMatchObject({ width: 6000, height: 4000 });

    const queued = page.waitForRequest(request =>
      new URL(request.url()).pathname === photos + '/creative' && request.method() === 'POST',
    );
    await page.getByRole('button', { name: 'Film Karesi', exact: true }).click();
    expect((await queued).postDataJSON().locale).toBe('tr');
    const preview = page.getByRole('img', { name: 'Film Karesi', exact: true });
    await expect.poll(() => preview.evaluate(image => (image as HTMLImageElement).naturalWidth),
      { timeout: 20_000 }).toBe(1800);
    const url = (await preview.getAttribute('src'))!;
    const previewJpeg = await page.request.get(url).then(response => response.body());
    const downloadJpeg = await page.request.get(url.replace(/\/preview$/, '/download')).then(response => response.body());
    expect(previewJpeg.equals(downloadJpeg)).toBe(true);

    await page.getByRole('button', { name: 'Oturumu bitir' }).click();
    await expect(page.getByRole('button', { name: 'Tek fotoğraf' })).toBeVisible();
  } finally {
    await page.request.post('/api/sessions/current/finish', {
      data: { state: 'canceled' }, headers: { 'X-Booth-Request': '1', Origin: baseURL! },
    });
  }
});
