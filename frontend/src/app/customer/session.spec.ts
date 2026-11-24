import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { describe, expect, it } from 'vitest';
import { I18n } from '../shared/i18n';
import { SessionPage } from './session';

describe('Session page', () => {
  it('keeps capture disabled when the unavailable state comes from the API', async () => {
    TestBed.configureTestingModule({ providers: [provideTranslateService(), provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    const fixture = TestBed.createComponent(SessionPage);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    const date = '2026-11-17T00:00:00Z';
    http.expectOne('/api/sessions/current').flush({
      id: 'test-session', state: 'active', experience: 'single', started_at: date, expires_at: date, ended_at: null,
    });
    await Promise.resolve();
    http.expectOne('/api/sessions/current/photos/latest').flush(null);
    await Promise.resolve();
    http.expectOne('/api/camera/status').flush({ state: 'unavailable', live_view: false, capture: false });
    await fixture.whenStable();
    fixture.detectChanges();
    const buttons = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>);
    expect(buttons.find(button => button.textContent?.includes('Take photo'))?.disabled).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('Camera unavailable');
    http.verify();
    fixture.destroy();
  });

  it('shows the session’s saved photo and download action after a reload', async () => {
    TestBed.configureTestingModule({ providers: [provideTranslateService(), provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    const fixture = TestBed.createComponent(SessionPage);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    const date = '2026-11-18T00:00:00Z';
    http.expectOne('/api/sessions/current').flush({
      id: 'test-session', state: 'active', experience: 'single', started_at: date, expires_at: date, ended_at: null,
    });
    await Promise.resolve();
    http.expectOne('/api/sessions/current/photos/latest').flush({
      id: 'saved-photo', captured_at: date, byte_size: 200, width: 6000, height: 4000,
    });
    await Promise.resolve();
    fixture.detectChanges();
    http.expectOne('/api/sessions/current/photos/creative?asset_id=saved-photo').flush([]);
    http.expectOne(request => request.url.endsWith('/print-jobs') && request.method === 'GET').flush(null);
    await fixture.whenStable();
    fixture.detectChanges();
    const image = fixture.nativeElement.querySelector('img') as HTMLImageElement;
    const download = fixture.nativeElement.querySelector('a[download]') as HTMLAnchorElement;
    expect(fixture.nativeElement.querySelector('.ai-preview').textContent).toContain('Coming Soon');
    expect(image.getAttribute('src')).toBe('/api/sessions/current/photos/saved-photo/preview');
    expect(download.getAttribute('href')).toBe('/api/sessions/current/photos/saved-photo/download');
    const phoneButton = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>)
      .find(button => button.textContent?.includes('Download on phone'))!;
    phoneButton.click();
    const phoneLink = http.expectOne('/api/sessions/current/photos/phone-links');
    expect(phoneLink.request.method).toBe('POST');
    expect(phoneLink.request.body).toEqual({ asset_id: 'saved-photo', kind: 'original' });
    const qr = 'data:image/png;base64,aW1hZ2U=';
    phoneLink.flush({ url: 'http://192.168.42.7:8001/d/test', qr_image: qr, expires_at: date });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('.phone-download img').getAttribute('src')).toBe(qr);
    const printButton = Array.from(fixture.nativeElement.querySelectorAll('button') as NodeListOf<HTMLButtonElement>)
      .find(button => button.textContent?.trim() === 'Print')!;
    printButton.click();
    const printReq = http.expectOne('/api/sessions/current/photos/print-jobs');
    expect(printReq.request.method).toBe('POST');
    expect(printReq.request.body).toEqual({ asset_id: 'saved-photo', kind: 'original' });
    printReq.flush({ id: 'print-job', state: 'failed', detail: 'The printer is offline. Check its power and connection, then try again.' });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('The printer is offline.');
    expect(fixture.nativeElement.textContent).toContain('Retry print');
    const i18n = TestBed.inject(I18n);
    try {
      i18n.select('tr');
      fixture.detectChanges();
      expect(fixture.nativeElement.textContent).toContain('Yazıcı çevrimdışı.');
      expect(fixture.nativeElement.textContent).toContain('Baskıyı yeniden dene');
      expect(fixture.nativeElement.querySelector('.phone-download img').getAttribute('src')).toBe(qr);
    } finally {
      i18n.select('en');
    }
    http.verify();
    fixture.destroy();
  });

  it('restores the next photo number in an interrupted filmstrip', async () => {
    TestBed.configureTestingModule({ providers: [provideTranslateService(), provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    const fixture = TestBed.createComponent(SessionPage);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    const date = '2026-11-18T00:00:00Z';
    http.expectOne('/api/sessions/current').flush({
      id: 'test-session', state: 'active', experience: 'filmstrip', started_at: date, expires_at: date, ended_at: null,
    });
    await Promise.resolve();
    http.expectOne('/api/sessions/current/photos/filmstrip').flush({ captured: 4, required: 6, result: null });
    await Promise.resolve();
    http.expectOne('/api/camera/status').flush({ state: 'unavailable', live_view: false, capture: false });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Photo 5 of 6');
    expect(fixture.nativeElement.textContent).toContain('Continue capture');
    http.verify();
    fixture.destroy();
  });

  it('restores the cue for the next unsaved Motion Study frame', async () => {
    TestBed.configureTestingModule({ providers: [provideTranslateService(), provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    const fixture = TestBed.createComponent(SessionPage);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    const date = '2026-11-19T00:00:00Z';
    http.expectOne('/api/sessions/current').flush({
      id: 'test-session', state: 'active', experience: 'filmstrip', started_at: date, expires_at: date, ended_at: null,
      multi_photo_plan: { experience: 'motion-study', version: 1, count: 4 },
      studio_directions: {
        title: 'Motion Study', introduction: 'Hold each pose until the shutter.', first_countdown: 3, next_countdown: 2,
        prompts: ['Set your starting pose.', 'Begin the move.', 'Reach the widest part of the move.', 'Hold your final pose.'],
      },
    });
    await Promise.resolve();
    http.expectOne('/api/sessions/current/photos/filmstrip').flush({ captured: 2, required: 4, result: null });
    await Promise.resolve();
    http.expectOne('/api/camera/status').flush({ state: 'unavailable', live_view: false, capture: false });
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain('Multi-Photo Studio · Motion Study');
    expect(fixture.nativeElement.textContent).toContain('Photo 3 of 4');
    expect(fixture.nativeElement.textContent).toContain('Reach the widest part of the move.');
    http.verify();
    fixture.destroy();
  });

  it('labels and explains a saved Time Sculpture pose sequence', async () => {
    TestBed.configureTestingModule({ providers: [provideTranslateService(), provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    const fixture = TestBed.createComponent(SessionPage);
    const http = TestBed.inject(HttpTestingController);
    fixture.detectChanges();
    const date = '2026-11-19T00:00:00Z';
    http.expectOne('/api/sessions/current').flush({
      id: 'test-session', state: 'active', experience: 'filmstrip', started_at: date, expires_at: date, ended_at: null,
      multi_photo_plan: { experience: 'time-sculpture', version: 1, count: 4 },
      studio_directions: { title: 'Time Sculpture', prompts: [], manual_advance: true },
    });
    await Promise.resolve();
    http.expectOne('/api/sessions/current/photos/filmstrip').flush({
      captured: 4, required: 4, result: {
        id: 'poses', width: 1800, height: 1200, byte_size: 200,
        fallback_reason: 'A pose or shadow crossed the marked area. Keep each pose and its shadow inside one area.',
      },
    });
    await Promise.resolve();
    fixture.detectChanges();
    http.expectOne(request => request.url.endsWith('/print-jobs') && request.method === 'GET').flush(null);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('h2').textContent).toBe('Your pose sequence');
    expect(fixture.nativeElement.textContent).toContain('A pose or shadow crossed the marked area.');
    expect(fixture.nativeElement.querySelector('img').getAttribute('alt')).toBe('Your three source poses');
    http.verify();
    fixture.destroy();
  });
});
