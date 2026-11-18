import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { describe, expect, it } from 'vitest';
import { AiPhotoPanel } from './ai-photo';

describe('AI photo preview', () => {
  it('requires consent and renders the completed local effect', async () => {
    TestBed.configureTestingModule({ providers: [provideHttpClient(), provideHttpClientTesting()] });
    const fixture = TestBed.createComponent(AiPhotoPanel);
    fixture.componentRef.setInput('photo', { id: 'original', width: 60, height: 40, byte_size: 100 });
    const http = TestBed.inject(HttpTestingController);
    const endpoint = '/api/sessions/current/photos/ai';
    const provider = { label: 'Local preview', sends_photo: false, privacy_url: null };
    const template = { id: 'cinematic-portrait', name: 'Cinematic portrait', description: 'Cool shadows.' };
    fixture.detectChanges();
    fixture.nativeElement.querySelector('button').click();
    http.expectOne(endpoint + '?asset_id=original').flush({ provider, templates: [{ ...template, job: null }] });
    await fixture.whenStable();
    fixture.detectChanges();
    const apply = fixture.nativeElement.querySelector('button') as HTMLButtonElement;
    expect(apply.disabled).toBe(true);
    expect(fixture.nativeElement.textContent).toContain('on this computer');
    apply.click();
    http.expectNone(endpoint);
    fixture.nativeElement.querySelector('input').click();
    fixture.detectChanges();
    apply.click();
    const queued = http.expectOne(endpoint);
    expect(queued.request.method).toBe('POST');
    expect(queued.request.body).toEqual({ asset_id: 'original', template_id: template.id, consent: true });
    const job = { id: 'effect', template_id: template.id, state: 'queued', detail: 'Waiting to process your photo.' };
    queued.flush(job);
    await fixture.whenStable();
    fixture.detectChanges();
    expect(fixture.nativeElement.textContent).toContain(job.detail);
    const refreshed = fixture.componentInstance.refresh();
    http.expectOne(endpoint + '?asset_id=original').flush({ provider, templates: [{
      ...template, job: { ...job, state: 'completed', detail: 'Your photo effect is ready.' },
    }] });
    await refreshed;
    fixture.detectChanges();
    const img = fixture.nativeElement.querySelector('img') as HTMLImageElement;
    const download = fixture.nativeElement.querySelector('a[download]') as HTMLAnchorElement;
    expect(img.getAttribute('src')).toBe(endpoint + '/effect/preview');
    expect(download.getAttribute('href')).toBe(endpoint + '/effect/download');
    http.verify();
    fixture.destroy();
  });
});
