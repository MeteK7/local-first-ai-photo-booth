import { provideHttpClient } from '@angular/common/http';
import { HttpTestingController, provideHttpClientTesting } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { describe, expect, it, vi } from 'vitest';
import { NewYearChoice } from '../shared/api';
import { I18n } from '../shared/i18n';
import { MultiPhotoStudio } from './multi-photo-studio';

const templates: NewYearChoice[] = ['midnight-memories', 'fresh-chapter', 'party-after-dark', 'sparkle-season',
  'radiant-welcome', 'hello-2027', 'glittering-welcome', 'welcome-celebration', 'champagne-cheers', 'new-years-eve',
  'burgundy-celebration', 'retro-confetti', 'aurora-celebration'].map(id => ({
  id: id as NewYearChoice['id'],
  default_plan: { experience: 'new-year', version: 1, template: id as NewYearChoice['id'], count: id === 'fresh-chapter' ? 5 : 4 },
  preview: '/api/sample/' + id, size: isLandscape(id) ? '6 × 4 in' : '4 × 6 in',
  preview_width: isLandscape(id) ? 720 : 480,
  preview_height: isLandscape(id) ? 480 : 720,
}));

function isLandscape(id: string): boolean {
  return ['glittering-welcome', 'burgundy-celebration', 'retro-confetti', 'aurora-celebration'].includes(id);
}

describe('Multi-photo New Year frames', () => {
  it.each([
    ['glittering-welcome', 'Parıltılı Karşılama'],
    ['burgundy-celebration', 'Bordo Kutlama'],
    ['retro-confetti', 'Retro Konfeti'],
    ['aurora-celebration', 'Kuzey Işıkları Kutlaması'],
  ])('opens the collection and sends the fixed-count plan for %s', async (id, label) => {
    TestBed.configureTestingModule({ providers: [provideTranslateService(), provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    const fixture = TestBed.createComponent(MultiPhotoStudio);
    const http = TestBed.inject(HttpTestingController);
    vi.spyOn(TestBed.inject(Router), 'navigateByUrl').mockResolvedValue(true);
    TestBed.inject(I18n).select('en');
    fixture.detectChanges();
    http.expectOne('/api/sessions/current').flush(null);
    await Promise.resolve();
    http.expectOne('/api/sessions/multi-photo-studio').flush({
      default_plan: { experience: 'signature-strip', version: 1, layout: 'vertical', count: 3 },
      counts: [2, 3, 4, 5, 6], layouts: [], new_year: templates,
    });
    await fixture.whenStable();
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const toggle = element.querySelector<HTMLButtonElement>('[aria-controls="multi-new-year-options"]')!;
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    toggle.click();
    fixture.detectChanges();
    const cards = element.querySelectorAll<HTMLButtonElement>('.multi-new-year-template');
    expect(cards.length).toBe(13);
    const previews = Array.from(cards, card => card.querySelector('img')!);
    expect(previews.map(image => Number(image.width) > Number(image.height))).toEqual([
      false, false, false, false, false, false, false, false, false, true, true, true, true,
    ]);
    cards[1].click();
    fixture.detectChanges();
    expect(cards[1].getAttribute('aria-pressed')).toBe('true');
    expect(element.querySelector('.multi-new-year-preview')?.getAttribute('src')).toContain('fresh-chapter');
    expect(element.querySelector('[aria-labelledby="photo-count-label"]')).toBeNull();
    expect(element.textContent).toContain('5 photos');
    TestBed.inject(I18n).select('tr');
    fixture.detectChanges();
    expect(element.textContent).toContain('Yeni Bir Sayfa');
    expect(element.textContent).toContain('5 fotoğraf');
    cards[2].click();
    fixture.detectChanges();
    expect(fixture.componentInstance.plan()).toEqual(templates[2].default_plan);
    const selected = templates.find(template => template.id === id)!;
    Array.from(cards).find(card => card.querySelector('img')?.getAttribute('src') === selected.preview)!.click();
    fixture.detectChanges();
    const landscape = element.querySelector<HTMLImageElement>('.multi-new-year-preview')!;
    expect(landscape.getAttribute('width')).toBe('720');
    expect(landscape.getAttribute('height')).toBe('480');
    expect(element.textContent).toContain(label);
    expect(element.textContent).toContain('6 × 4');
    expect(element.textContent).toContain('4 fotoğraf');
    element.querySelector<HTMLButtonElement>('.multi-photo-actions button')!.click();
    const request = http.expectOne('/api/sessions');
    expect(request.request.body).toEqual({ experience: 'filmstrip', multi_photo_plan: selected.default_plan });
    request.flush({});
    await fixture.whenStable();
    TestBed.inject(I18n).select('en');
    http.verify();
    fixture.destroy();
  });
});
