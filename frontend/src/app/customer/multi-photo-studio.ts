import { Component, inject, OnInit, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Api, message, MultiPhotoCatalog, SignatureStripPlan } from '../shared/api';

@Component({
  selector: 'app-multi-photo-studio',
  imports: [RouterLink],
  template: `
    <section class="panel multi-photo" aria-labelledby="multi-photo-title">
      <header class="multi-photo-header">
        <h1 id="multi-photo-title">Multi-Photo Studio</h1>
        <p>Classic Collection</p>
        <h2>Signature Strip</h2>
        <p>Choose how many photos to take and how to arrange them.</p>
      </header>
      @if (catalog(); as options) {
        @if (plan(); as selected) {
          <div class="multi-photo-field">
            <h3 id="photo-count-label">Number of photos</h3>
            <div class="multi-photo-counts" role="group" aria-labelledby="photo-count-label">
              @for (count of options.counts; track count) {
                <button type="button" class="secondary" [aria-pressed]="count === selected.count" [disabled]="starting()"
                        (click)="plan.set({ ...selected, count })">{{ count }}</button>
              }
            </div>
          </div>
          <div class="multi-photo-field">
            <h3 id="photo-layout-label">Layout</h3>
            <div class="multi-photo-layouts" role="group" aria-labelledby="photo-layout-label">
              @for (option of options.layouts; track option.id) {
                <button type="button" class="secondary multi-photo-layout" [aria-pressed]="option.id === selected.layout"
                        [disabled]="starting()" (click)="plan.set({ ...selected, layout: option.id })">
                  <span class="multi-photo-mat" aria-hidden="true">
                    <span class="multi-photo-sheet" [class]="option.id" [style.aspect-ratio]="option.width + ' / ' + option.height">
                      @for (frame of option.frames[selected.count]; track $index) {
                        <span class="multi-photo-cell" [style.left.%]="100 * frame[0] / option.width"
                              [style.top.%]="100 * frame[1] / option.height" [style.width.%]="100 * frame[2] / option.width"
                              [style.height.%]="100 * frame[3] / option.height"></span>
                      }
                    </span>
                  </span>
                  <span>{{ option.name }}</span>
                  <small>{{ option.size }}</small>
                </button>
              }
            </div>
          </div>
          <div class="actions multi-photo-actions">
            <button type="button" class="primary" [disabled]="starting()" (click)="start(selected)">
              {{ starting() ? 'Opening session…' : 'Continue to camera' }}
            </button>
            <a class="secondary" routerLink="/">Back to welcome</a>
          </div>
        }
      } @else if (loading()) {
        <p role="status">Loading layouts…</p>
      } @else {
        <div class="actions">
          <button type="button" class="primary" (click)="load()">Try again</button>
          <a class="secondary" routerLink="/">Back to welcome</a>
        </div>
      }
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    </section>
  `,
})
export class MultiPhotoStudio implements OnInit {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  readonly catalog = signal<MultiPhotoCatalog | null>(null);
  readonly plan = signal<SignatureStripPlan | null>(null);
  readonly loading = signal(true);
  readonly starting = signal(false);
  readonly error = signal('');

  ngOnInit(): void { void this.load(); }

  async load(): Promise<void> {
    this.loading.set(true);
    this.error.set('');
    try {
      if (await this.api.current()) {
        await this.router.navigateByUrl('/session', { replaceUrl: true });
        return;
      }
      const catalog = await this.api.multiPhotoCatalog();
      this.plan.set(catalog.default_plan);
      this.catalog.set(catalog);
    } catch (error) {
      this.error.set(message(error, 'Could not load the studio layouts. Please try again.'));
    } finally {
      this.loading.set(false);
    }
  }

  async start(plan: SignatureStripPlan): Promise<void> {
    if (this.starting()) return;
    this.starting.set(true);
    this.error.set('');
    try {
      await this.api.start('filmstrip', plan);
      await this.router.navigateByUrl('/session');
    } catch (error) {
      this.error.set(message(error, 'Could not open your session. Please try again.'));
    } finally {
      this.starting.set(false);
    }
  }
}
