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
  it('replaces Motion Study immediately when opening New Year and retains the chosen frame when reopening', async () => {
    TestBed.configureTestingModule({ providers: [provideTranslateService(), provideRouter([]), provideHttpClient(), provideHttpClientTesting()] });
    const fixture = TestBed.createComponent(MultiPhotoStudio);
    const http = TestBed.inject(HttpTestingController);
    TestBed.inject(I18n).select('en');
    fixture.detectChanges();
    http.expectOne('/api/sessions/current').flush(null);
    await Promise.resolve();
    http.expectOne('/api/sessions/multi-photo-studio').flush({
      default_plan: { experience: 'signature-strip', version: 1, layout: 'vertical', count: 3 },
      counts: [2, 3, 4, 5, 6], layouts: [],
      new_year: [templates[6], ...templates.filter(template => template !== templates[6])],
      creative: [{
        default_plan: { experience: 'motion-study', version: 1, layout: 'contact-stack', count: 4 },
        name: 'Motion Study', description: '', counts: [4, 5, 6],
        composition: { size: '6 × 4 in', width: 720, height: 480, frames: {} },
      }],
      motion_layouts: [{
        id: 'contact-stack', name: 'Contact Stack', description: '', counts: [4, 5, 6],
        previews: { 4: '/api/sample/motion-study' },
      }],
    });
    await fixture.whenStable();
    fixture.detectChanges();
    const element = fixture.nativeElement as HTMLElement;
    const motion = element.querySelector<HTMLButtonElement>('[aria-labelledby="creative-collection"] button')!;
    motion.click();
    fixture.detectChanges();
    expect(element.querySelector('.motion-study-controls')).not.toBeNull();
    expect(element.querySelector('.motion-study-print-sample')).not.toBeNull();
    const motionDescription = element.querySelector('.multi-photo-description')!.textContent;

    const toggle = element.querySelector<HTMLButtonElement>('[aria-controls="multi-new-year-options"]')!;
    toggle.click();
    fixture.detectChanges();
    expect(toggle.getAttribute('aria-pressed')).toBe('true');
    expect(motion.getAttribute('aria-pressed')).toBe('false');
    expect(element.querySelector('.motion-study-controls')).toBeNull();
    expect(element.querySelector('.motion-study-print-sample')).toBeNull();
    expect(element.querySelector('[aria-labelledby="photo-count-label"]')).toBeNull();
    expect(element.querySelector('.multi-photo-description')!.textContent).not.toBe(motionDescription);
    expect(fixture.componentInstance.plan()).toEqual(templates[0].default_plan);
    expect(element.querySelector('.multi-new-year-preview')?.getAttribute('src')).toBe(templates[0].preview);

    element.querySelectorAll<HTMLButtonElement>('.multi-new-year-template')[1].click();
    fixture.detectChanges();
    toggle.click();
    fixture.detectChanges();
    expect(element.querySelector('#multi-new-year-options')).toBeNull();
    toggle.click();
    fixture.detectChanges();
    expect(fixture.componentInstance.plan()).toEqual(templates[1].default_plan);
    expect(element.querySelector('.multi-new-year-template[aria-pressed="true"] img')?.getAttribute('src')).toBe(templates[1].preview);

    motion.click();
    fixture.detectChanges();
    expect(toggle.getAttribute('aria-expanded')).toBe('false');
    expect(toggle.getAttribute('aria-pressed')).toBe('false');
    expect(element.querySelector('#multi-new-year-options')).toBeNull();
    expect(element.querySelector('.motion-study-print-sample')).not.toBeNull();
    http.expectNone('/api/sessions');
    http.verify();
    fixture.destroy();
  });

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
