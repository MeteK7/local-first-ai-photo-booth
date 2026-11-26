import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { describe, expect, it, vi } from 'vitest';
import { I18n } from '../shared/i18n';
import { CreativeStudio } from './creative-studio';

const photos = '/api/sessions/current/photos';
const catalog = [
  { id: 'portrait-atlas', name: 'Portrait Atlas', description: 'Editorial detail crops.', result: null },
  { id: 'parallel-portrait', name: 'Parallel Portrait', description: 'Paired portrait.', result: null },
  { id: 'film-frame', name: 'The Film Frame', description: 'Film grain and a matte.', result: null },
  { id: 'classic-filter', name: 'Classic Filter', description: 'Warm highlights.', result: null },
  { id: 'hazar-station-portrait', name: 'Station · Portrait', description: '', category: 'frame', result: null },
  { id: 'hazar-station-landscape', name: 'Station · Landscape', description: '', category: 'frame', result: null },
  { id: 'hazar-travel-portrait', name: 'Safe Travels · Portrait', description: '', category: 'frame', result: null },
  { id: 'hazar-travel-landscape', name: 'Safe Travels · Landscape', description: '', category: 'frame', result: null },
  { id: 'hazar-roadside-landscape', name: 'Roadside · Landscape', description: '', category: 'frame', result: null },
  { id: 'new-year-golden-midnight-portrait', name: 'Golden Midnight · Portrait', description: '', category: 'new-year-frame', result: null },
  { id: 'new-year-ornate-2027-portrait', name: 'Ornate 2027 · Portrait', description: '', category: 'new-year-frame', result: null },
  { id: 'new-year-pine-cones-portrait', name: 'Festive Pine Cones · Portrait', description: '', category: 'new-year-frame', result: null },
  { id: 'new-year-fireworks-portrait', name: 'Fireworks Celebration · Portrait', description: '', category: 'new-year-frame', result: null },
  { id: 'new-year-colorful-2027-portrait', name: 'Colorful 2027 · Portrait', description: '', category: 'new-year-frame', result: null },
  { id: 'new-year-winter-garland-landscape', name: 'Winter Garland · Landscape', description: '', category: 'new-year-frame', result: null },
  { id: 'new-year-winter-drive-blue-landscape', name: 'Winter Drive · Blue Car', description: '', category: 'new-year-frame', result: null },
  { id: 'new-year-winter-drive-red-landscape', name: 'Winter Drive · Red Car', description: '', category: 'new-year-frame', result: null },
  { id: 'new-year-bright-blue-landscape', name: 'Bright Blue · 2027', description: '', category: 'new-year-frame', result: null },
  { id: 'new-year-vibrant-2027-landscape', name: 'Vibrant Celebration · 2027', description: '', category: 'new-year-frame', result: null },
  { id: 'new-year-cozy-winter-landscape', name: 'Cozy Winter · 2027', description: '', category: 'new-year-frame', result: null },
].map(item => ({
  ...item,
  ...(item.category ? {
    preview: photos + '/creative/frames/' + item.id + '/preview?version=1',
    preview_width: item.id.endsWith('-portrait') ? 240 : 360,
    preview_height: item.id.endsWith('-portrait') ? 360 : 240,
  } : {}),
}));

async function setUp() {
  TestBed.configureTestingModule({ providers: [provideTranslateService(), provideHttpClient(), provideHttpClientTesting()] });
  const fixture = TestBed.createComponent(CreativeStudio);
  fixture.componentRef.setInput('photo', { id: 'source', width: 60, height: 40, byte_size: 100 });
  const http = TestBed.inject(HttpTestingController);
  const element = fixture.nativeElement as HTMLElement;
  const button = (label: string) => Array.from(element.querySelectorAll('button'))
    .find(item => item.getAttribute('aria-label') === label || item.textContent.trim() === label)!;
  fixture.detectChanges();
  http.expectOne(photos + '/creative?asset_id=source').flush(catalog);
  http.expectOne(photos + '/print-jobs?asset_id=source&kind=original').flush(null);
  await vi.waitFor(() => {
    fixture.detectChanges();
    expect(button('Original').disabled).toBe(false);
  });
  return { fixture, http, element, button };
}

describe('Creative Studio', () => {
  it('opens the Hazar frame choices from a single button without changing the photo', async () => {
    const { fixture, http, element, button } = await setUp();
    const toggle = button('Hazar Frames');
    const frames = element.querySelector<HTMLElement>('#studio-hazar-options')!;
    expect(toggle.parentElement).toBe(button('Portrait Atlas').parentElement);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(frames.hidden).toBe(true);
    expect(element.querySelectorAll('.studio-frame-preview img').length).toBe(0);
    toggle.click();
    fixture.detectChanges();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(frames.hidden).toBe(false);
    expect(Array.from(frames.querySelectorAll('button'), item => item.textContent.trim())).toEqual([
      'Station · Portrait', 'Safe Travels · Portrait', 'Station · Landscape', 'Safe Travels · Landscape',
      'Roadside · Landscape',
    ]);
    const thumbnails = Array.from(frames.querySelectorAll<HTMLImageElement>('.studio-frame-preview img'));
    expect(thumbnails.length).toBe(5);
    expect(thumbnails.map(image => image.getAttribute('src'))).toEqual([
      'hazar-station-portrait', 'hazar-travel-portrait', 'hazar-station-landscape',
      'hazar-travel-landscape', 'hazar-roadside-landscape',
    ].map(id => photos + '/creative/frames/' + id + '/preview?version=1'));
    expect(thumbnails.map(image => Number(image.width) > Number(image.height))).toEqual([false, false, true, true, true]);
    expect(button('Original').getAttribute('aria-pressed')).toBe('true');
    http.expectNone(request => request.method === 'POST');
    button('Roadside · Landscape').click();
    const request = http.expectOne(photos + '/creative');
    expect(request.request.body).toMatchObject({ asset_id: 'source', treatment: 'hazar-roadside-landscape' });
    request.flush({ id: 'roadside', kind: 'creative', state: 'completed', detail: 'Your treatment is ready.' });
    await fixture.whenStable();
    fixture.detectChanges();
    http.expectOne(photos + '/print-jobs?asset_id=roadside&kind=creative').flush(null);
    expect(element.querySelector('.photo-stage img')?.getAttribute('src')).toBe(photos + '/creative/roadside/preview');
    expect(button('Roadside · Landscape').getAttribute('aria-pressed')).toBe('true');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(toggle.disabled).toBe(false);
    });
    toggle.click();
    fixture.detectChanges();
    expect(frames.hidden).toBe(true);
    expect(element.querySelectorAll('.studio-frame-preview img').length).toBe(0);
    expect(element.querySelector('.photo-stage img')?.getAttribute('src')).toBe(photos + '/creative/roadside/preview');
    http.verify();
    fixture.destroy();
  });

  it('uses the latest selection for preview, download, phone QR and printing', async () => {
    const { fixture, http, element, button } = await setUp();
    expect(element.querySelector('.photo-stage img')?.getAttribute('src')).toBe(photos + '/source/preview');
    button('The Film Frame').click();
    const film = http.expectOne(photos + '/creative');
    expect(film.request.body).toEqual({ asset_id: 'source', treatment: 'film-frame', locale: 'en' });
    fixture.detectChanges();
    expect(element.textContent).toContain('Preparing your photo');
    expect(element.querySelector('a[download]')).toBeNull();

    button('Parallel Portrait').click();
    const parallel = http.expectOne(photos + '/creative');
    expect(parallel.request.body).toEqual({ asset_id: 'source', treatment: 'parallel-portrait', locale: 'en' });
    parallel.flush({ id: 'parallel', kind: 'creative', state: 'completed', detail: 'Your treatment is ready.' });
    film.flush({ id: 'film', kind: 'creative', state: 'completed', detail: 'Your treatment is ready.' });
    await fixture.whenStable();
    fixture.detectChanges();
    http.expectOne(photos + '/print-jobs?asset_id=parallel&kind=creative').flush(null);
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(button('Print').disabled).toBe(false);
    });
    expect(element.querySelector('.photo-stage img')?.getAttribute('src')).toBe(photos + '/creative/parallel/preview');
    expect(element.querySelector('a[download]')?.getAttribute('href')).toBe(photos + '/creative/parallel/download');
    button('Download on phone').click();
    const phone = http.expectOne(photos + '/phone-links');
    expect(phone.request.body).toEqual({ asset_id: 'parallel', kind: 'creative' });
    phone.flush({ url: 'http://192.168.1.2/d/fixture', qr_image: 'data:image/png;base64,aW1hZ2U=',
                  expires_at: '2026-11-19T00:05:00Z' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(element.querySelector('[aria-label="Parallel Portrait phone download"]')).not.toBeNull();

    button('Print').click();
    const print = http.expectOne(photos + '/print-jobs');
    expect(print.request.body).toEqual({ asset_id: 'parallel', kind: 'creative' });
    print.flush({ id: 'print', state: 'sent', detail: 'Sent to the printer.' });
    await fixture.whenStable();
    fixture.detectChanges();
    button('Original').click();
    fixture.detectChanges();
    http.expectOne(photos + '/print-jobs?asset_id=source&kind=original').flush(null);
    expect(element.querySelector('.photo-stage img')?.getAttribute('src')).toBe(photos + '/source/preview');
    expect(element.querySelector('.phone-download')).toBeNull();
    http.verify();
    fixture.destroy();
  });

  it.each([
    ['Winter Drive · Red Car', 'new-year-winter-drive-red-landscape'],
    ['Bright Blue · 2027', 'new-year-bright-blue-landscape'],
    ['Vibrant Celebration · 2027', 'new-year-vibrant-2027-landscape'],
    ['Cozy Winter · 2027', 'new-year-cozy-winter-landscape'],
    ['Festive Pine Cones · Portrait', 'new-year-pine-cones-portrait'],
    ['Fireworks Celebration · Portrait', 'new-year-fireworks-portrait'],
    ['Colorful 2027 · Portrait', 'new-year-colorful-2027-portrait'],
  ])('opens the New Year collection and selects %s', async (label, treatment) => {
    const { fixture, http, element, button } = await setUp();
    const newYear = button('New Year Frames');
    const hazar = button('Hazar Frames');
    const frames = element.querySelector<HTMLElement>('#studio-new-year-options')!;
    expect(newYear.getAttribute('aria-expanded')).toBe('false');
    expect(frames.hidden).toBe(true);
    hazar.click();
    fixture.detectChanges();
    expect(hazar.getAttribute('aria-expanded')).toBe('true');
    newYear.click();
    fixture.detectChanges();
    expect(hazar.getAttribute('aria-expanded')).toBe('false');
    expect(newYear.getAttribute('aria-expanded')).toBe('true');
    expect(frames.hidden).toBe(false);
    const thumbnails = Array.from(frames.querySelectorAll<HTMLImageElement>('.studio-frame-preview img'));
    expect(thumbnails.length).toBe(11);
    expect(thumbnails.every(image => image.getAttribute('src')?.includes('/frames/new-year-'))).toBe(true);
    expect(thumbnails.map(image => Number(image.width) > Number(image.height))).toEqual([
      false, false, false, false, false, true, true, true, true, true, true,
    ]);
    expect(Array.from(frames.querySelectorAll('button'), item => item.textContent.trim())).toEqual([
      'Golden Midnight · Portrait', 'Ornate 2027 · Portrait', 'Festive Pine Cones · Portrait',
      'Fireworks Celebration · Portrait', 'Colorful 2027 · Portrait', 'Winter Garland · Landscape',
      'Winter Drive · Blue Car', 'Winter Drive · Red Car',
      'Bright Blue · 2027', 'Vibrant Celebration · 2027', 'Cozy Winter · 2027',
    ]);
    http.expectNone(request => request.method === 'POST');
    button(label).click();
    const render = http.expectOne(photos + '/creative');
    expect(render.request.body).toMatchObject({ asset_id: 'source', treatment });
    render.flush({ id: 'red-drive', kind: 'creative', state: 'completed', detail: 'Your treatment is ready.' });
    await fixture.whenStable();
    fixture.detectChanges();
    http.expectOne(photos + '/print-jobs?asset_id=red-drive&kind=creative').flush(null);
    expect(element.querySelector('.photo-stage img')?.getAttribute('src')).toBe(photos + '/creative/red-drive/preview');
    expect(element.querySelector('a[download]')?.getAttribute('href')).toBe(photos + '/creative/red-drive/download');
    http.verify();
    fixture.destroy();
  });

  it('polls queued treatments and offers a retry after processing fails', async () => {
    const { fixture, http, element, button } = await setUp();
    button('Portrait Atlas').click();
    const job = { id: 'atlas', kind: 'creative', state: 'queued', detail: 'Waiting to prepare your photo.' };
    http.expectOne(photos + '/creative').flush(job);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(element.textContent).toContain(job.detail);
    const i18n = TestBed.inject(I18n);
    try {
      i18n.select('tr');
      fixture.detectChanges();
      expect(element.textContent).toContain('Fotoğrafınız hazırlanmak üzere sırada.');
      expect(button('Portre Atlası').getAttribute('aria-pressed')).toBe('true');
      http.expectNone(request => request.method === 'POST');
    } finally {
      i18n.select('en');
    }
    const refreshed = fixture.componentInstance.refresh();
    http.expectOne(photos + '/creative?asset_id=source').flush([
      { ...catalog[0], result: { ...job, state: 'failed', detail: 'This treatment could not be prepared.' } },
      ...catalog.slice(1),
    ]);
    await refreshed;
    fixture.detectChanges();
    expect(element.textContent).toContain('This treatment could not be prepared.');
    button('Try again').click();
    const retry = http.expectOne(photos + '/creative');
    expect(retry.request.body).toEqual({ asset_id: 'source', treatment: 'portrait-atlas', locale: 'en' });
    retry.flush(job);
    await fixture.whenStable();
    http.verify();
    fixture.destroy();
  });
});
