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
];

async function setUp() {
  TestBed.configureTestingModule({ providers: [provideTranslateService(), provideHttpClient(), provideHttpClientTesting()] });
  const fixture = TestBed.createComponent(CreativeStudio);
  fixture.componentRef.setInput('photo', { id: 'source', width: 60, height: 40, byte_size: 100 });
  const http = TestBed.inject(HttpTestingController);
  const element = fixture.nativeElement as HTMLElement;
  const button = (label: string) => Array.from(element.querySelectorAll('button'))
    .find(item => item.textContent.trim() === label)!;
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
  it('opens the four Hazar frame choices from a single button without changing the photo', async () => {
    const { fixture, http, element, button } = await setUp();
    const toggle = button('Hazar Frames');
    const frames = element.querySelector<HTMLElement>('#studio-hazar-options')!;
    expect(toggle.parentElement).toBe(button('Portrait Atlas').parentElement);
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(frames.hidden).toBe(true);
    toggle.click();
    fixture.detectChanges();
    expect(toggle.getAttribute('aria-expanded')).toBe('true');
    expect(frames.hidden).toBe(false);
    expect(Array.from(frames.querySelectorAll('button'), item => item.textContent.trim())).toEqual([
      'Station · Portrait', 'Station · Landscape', 'Safe Travels · Portrait', 'Safe Travels · Landscape',
    ]);
    expect(button('Original').getAttribute('aria-pressed')).toBe('true');
    http.expectNone(request => request.method === 'POST');
    button('Safe Travels · Portrait').click();
    const request = http.expectOne(photos + '/creative');
    expect(request.request.body).toMatchObject({ asset_id: 'source', treatment: 'hazar-travel-portrait' });
    request.flush({ id: 'travel', kind: 'creative', state: 'completed', detail: 'Your treatment is ready.' });
    await fixture.whenStable();
    fixture.detectChanges();
    http.expectOne(photos + '/print-jobs?asset_id=travel&kind=creative').flush(null);
    expect(element.querySelector('img')?.getAttribute('src')).toBe(photos + '/creative/travel/preview');
    expect(button('Safe Travels · Portrait').getAttribute('aria-pressed')).toBe('true');
    await vi.waitFor(() => {
      fixture.detectChanges();
      expect(toggle.disabled).toBe(false);
    });
    toggle.click();
    fixture.detectChanges();
    expect(frames.hidden).toBe(true);
    expect(element.querySelector('img')?.getAttribute('src')).toBe(photos + '/creative/travel/preview');
    http.verify();
    fixture.destroy();
  });

  it('uses the latest selection for preview, download, phone QR and printing', async () => {
    const { fixture, http, element, button } = await setUp();
    expect(element.querySelector('img')?.getAttribute('src')).toBe(photos + '/source/preview');
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
    expect(element.querySelector('img')?.getAttribute('src')).toBe(photos + '/creative/parallel/preview');
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
    expect(element.querySelector('img')?.getAttribute('src')).toBe(photos + '/source/preview');
    expect(element.querySelector('.phone-download')).toBeNull();
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
