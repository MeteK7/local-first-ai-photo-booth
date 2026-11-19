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

const creativeRuns = [
  { name: 'Between Frames', id: 'between-frames', cues: ['Hold a calm expression.', 'Change your gaze.', 'Break into a laugh.'] },
  { name: 'Motion Study', id: 'motion-study', cues: [
    'Set your starting pose.', 'Begin the move.', 'Reach the widest part of the move.', 'Hold your final pose.',
  ] },
  { name: 'Mini Scene', id: 'mini-scene', manual: true, cues: [
    'Setup · Show us who you are.', 'Action · Make something happen.',
    'Reaction · Show how you feel about it.', 'Ending · Give the story an ending.',
  ] },
];

for (const { name, id, cues, manual } of creativeRuns) {
  test(`Creative Collection captures and delivers ${name} on the physical D5600`, async ({ page, baseURL }) => {
    test.skip(process.env['PHOTOBOOTH_HARDWARE_TESTS'] !== '1', 'This test fires a real shutter.');
    test.setTimeout(145_000);
    const photos = '/api/sessions/current/photos';
    const headers = { 'X-Booth-Request': '1', Origin: baseURL! };
    const captures: { slot: number; status: number }[] = [];
    page.on('response', response => {
      if (new URL(response.url()).pathname === photos && response.request().method() === 'POST') {
        captures.push({ slot: response.request().postDataJSON().slot, status: response.status() });
      }
    });

    try {
      await page.goto('/multi-photo-studio');
      await page.getByRole('button', { name }).click();
      if (!manual) await page.getByRole('button', { name: String(cues.length), exact: true }).click();
      await page.getByRole('button', { name: 'Continue to camera' }).click();
      const firstCue = page.getByText(cues[0], { exact: true });
      await expect(firstCue).toBeVisible();
      const shutter = page.getByRole('button', { name: manual ? 'Take first photo' : `Take ${cues.length} photos` });
      await expect(shutter).toBeEnabled({ timeout: 20_000 });
      await shutter.click();
      for (const cue of cues.slice(1)) {
        await expect(page.getByText(cue, { exact: true })).toBeVisible({ timeout: 30_000 });
        if (manual) await page.getByRole('button', { name: 'Take next photo' }).click();
      }

      const preview = page.getByAltText(`Your ${name} composition`);
      await expect(preview.or(page.locator('.session > .error'))).toBeVisible({ timeout: 50_000 });
      expect(await page.locator('.session > .error').allTextContents()).toEqual([]);
      expect(captures).toEqual(cues.map((_, index) => ({ slot: index + 1, status: 201 })));
      await expect.poll(() => preview.evaluate(image => [
        (image as HTMLImageElement).naturalWidth, (image as HTMLImageElement).naturalHeight,
      ])).toEqual([1800, 1200]);
      const previewUrl = (await preview.getAttribute('src'))!;
      const jpeg = await (await page.request.get(previewUrl)).body();
      const pendingDownload = page.waitForEvent('download');
      await page.getByRole('link', { name: 'Download composition' }).click();
      const download = await pendingDownload;
      expect(download.suggestedFilename()).toBe(`${id}.jpg`);
      expect((await readFile((await download.path())!)).equals(jpeg)).toBe(true);

      if (process.env['PHOTOBOOTH_HARDWARE_QR_TESTS'] === '1') {
        const pendingGrant = page.waitForResponse(response => new URL(response.url()).pathname === `${photos}/phone-links`);
        await page.getByRole('button', { name: 'Download on phone' }).click();
        const grantResponse = await pendingGrant;
        expect(grantResponse.status()).toBe(201);
        const grant = await grantResponse.json();
        const phonePhoto = await page.request.get(grant.url, { timeout: 5000 });
        expect(phonePhoto.status()).toBe(200);
        expect((await phonePhoto.body()).equals(jpeg)).toBe(true);
      }
      await expect(page.getByRole('button', { name: 'Print', exact: true })).toBeEnabled();
      await page.getByRole('button', { name: 'Finish session' }).click();
      await expect(page.getByRole('link', { name: 'Multi-Photo Studio' })).toBeVisible();
    } finally {
      await page.request.post('/api/sessions/current/finish', { data: { state: 'canceled' }, headers });
    }
  });
}
