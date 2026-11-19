import { readFile } from 'node:fs/promises';
import { expect, test } from '@playwright/test';

test('takes and downloads a full-resolution photo on the physical D5600', async ({ page, browser, baseURL }) => {
  test.skip(process.env['PHOTOBOOTH_HARDWARE_TESTS'] !== '1', 'This test fires a real shutter.');
  test.setTimeout(60_000);
  const photos = '/api/sessions/current/photos';
  const headers = { 'X-Booth-Request': '1', Origin: baseURL! };
  const other = await browser.newContext({ baseURL });
  try {
    await page.goto('/');
    await page.getByRole('button', { name: 'Single photo' }).click();
    const liveView = page.getByAltText('Live view from the booth camera');
    await expect.poll(() => liveView.evaluate(image => (image as HTMLImageElement).naturalWidth), {
      timeout: 15_000,
    }).toBeGreaterThan(0);

    const pendingCapture = page.waitForResponse(response =>
      new URL(response.url()).pathname === photos && response.request().method() === 'POST',
    );
    await page.getByRole('button', { name: 'Take photo' }).click();
    await expect(page.getByText('3', { exact: true })).toBeVisible();
    const capture = await pendingCapture;
    expect(capture.status(), await capture.text()).toBe(201);
    const photo = await capture.json();
    expect(photo).toMatchObject({ width: 6000, height: 4000 });

    const preview = page.getByAltText('Your captured photo');
    await expect.poll(() => preview.evaluate(image => (image as HTMLImageElement).naturalWidth)).toBeGreaterThan(0);
    const previewResponse = await page.request.get(`${photos}/${photo.id}/preview`);
    expect(previewResponse.ok()).toBe(true);
    const original = await previewResponse.body();
    const pendingDownload = page.waitForEvent('download');
    await page.getByRole('link', { name: 'Download photo' }).click();
    const download = await pendingDownload;
    expect(download.suggestedFilename()).toBe('photo-booth.jpg');
    expect((await readFile((await download.path())!)).equals(original)).toBe(true);

    expect((await other.request.post('/api/sessions', { data: {}, headers })).status()).toBe(201);
    expect((await other.request.get(`${photos}/${photo.id}/download`)).status()).toBe(404);
    await page.reload();
    await expect(preview).toBeVisible();
    await page.getByRole('button', { name: 'Finish session' }).click();
    await expect(page.getByRole('button', { name: 'Single photo' })).toBeVisible();
    expect((await page.request.get(`${photos}/${photo.id}/download`)).status()).toBe(404);
  } finally {
    const canceled = { data: { state: 'canceled' }, headers };
    await Promise.all([
      page.request.post('/api/sessions/current/finish', canceled),
      other.request.post('/api/sessions/current/finish', canceled),
    ]);
    await other.close();
  }
});

test('builds a vertical Signature Strip from three physical D5600 captures', async ({ page, baseURL }) => {
  test.skip(process.env['PHOTOBOOTH_HARDWARE_TESTS'] !== '1', 'This test fires three real shutter releases.');
  test.setTimeout(100_000);
  const photos = '/api/sessions/current/photos';
  const headers = { 'X-Booth-Request': '1', Origin: baseURL! };
  const originals: Promise<{ id: string; width: number; height: number }>[] = [];
  const responses: number[] = [];
  page.on('response', response => {
    if (new URL(response.url()).pathname !== photos || response.request().method() !== 'POST') return;
    responses.push(response.status());
    if (response.ok()) originals.push(response.json());
  });
  try {
    await page.goto('/');
    await page.getByRole('link', { name: 'Multi-Photo Studio' }).click();
    await page.getByRole('button', { name: 'Continue to camera' }).click();
    await expect(page.getByText('Photo 1 of 3', { exact: true })).toBeVisible();
    const start = page.getByRole('button', { name: 'Take 3 photos' });
    await expect(start).toBeEnabled({ timeout: 15_000 });
    await start.click();

    const preview = page.getByAltText('Your Signature Strip composition');
    await expect(preview).toBeVisible({ timeout: 75_000 });
    expect(responses).toEqual([201, 201, 201]);
    const photosTaken = await Promise.all(originals);
    expect(new Set(photosTaken.map(photo => photo.id)).size).toBe(3);
    expect(photosTaken.every(photo => photo.width === 6000 && photo.height === 4000)).toBe(true);
    await expect.poll(() => preview.evaluate(image => [(image as HTMLImageElement).naturalWidth,
      (image as HTMLImageElement).naturalHeight])).toEqual([600, 1800]);

    await page.reload();
    await expect(preview).toBeVisible();
    const downloadEvent = page.waitForEvent('download');
    const downloadLink = page.getByRole('link', { name: 'Download composition' });
    const url = (await downloadLink.getAttribute('href'))!;
    await downloadLink.click();
    const download = await downloadEvent;
    expect(download.suggestedFilename()).toBe('signature-strip.jpg');
    expect((await readFile((await download.path())!)).length).toBeGreaterThan(0);
    await page.getByRole('button', { name: 'Finish session' }).click();
    await expect(page.getByRole('button', { name: 'Single photo' })).toBeVisible();
    expect((await page.request.get(url)).status()).toBe(404);
  } finally {
    await page.request.post('/api/sessions/current/finish', { data: { state: 'canceled' }, headers });
  }
});
