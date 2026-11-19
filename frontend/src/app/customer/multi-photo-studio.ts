import { Component, computed, inject, input, OnInit, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Api, CapturePlan, CompositionGeometry, message, MultiPhotoCatalog } from '../shared/api';

@Component({
  selector: 'app-composition-preview',
  template: `
    <span class="multi-photo-mat" aria-hidden="true">
      <span class="multi-photo-sheet" [class]="shape()" [style.aspect-ratio]="geometry().width + ' / ' + geometry().height">
        @for (frame of geometry().frames[count()]; track $index) {
          <span class="multi-photo-cell" [style.left.%]="100 * frame[0] / geometry().width"
                [style.top.%]="100 * frame[1] / geometry().height" [style.width.%]="100 * frame[2] / geometry().width"
                [style.height.%]="100 * frame[3] / geometry().height"></span>
        }
      </span>
    </span>
  `,
})
class CompositionPreview {
  readonly geometry = input.required<CompositionGeometry>();
  readonly count = input.required<number>();
  readonly shape = input.required<string>();
}

@Component({
  selector: 'app-multi-photo-studio',
  imports: [RouterLink, CompositionPreview],
  template: `
    <section class="panel multi-photo" aria-labelledby="multi-photo-title">
      <header class="multi-photo-header">
        <h1 id="multi-photo-title">Multi-Photo Studio</h1>
      </header>
      @if (catalog(); as options) {
        @if (plan(); as selected) {
          <div class="multi-photo-collections">
            <div class="multi-photo-collection" role="group" aria-labelledby="classic-collection">
              <h2 id="classic-collection">Classic Collection</h2>
              <button class="secondary" type="button" [aria-pressed]="selected.experience === 'signature-strip'"
                      [disabled]="starting()" (click)="chooseExperience(options.default_plan)">Signature Strip</button>
            </div>
            <div class="multi-photo-collection multi-photo-creative-modes" role="group" aria-labelledby="creative-collection">
              <h2 id="creative-collection">Creative Collection</h2>
              @for (option of options.creative ?? []; track option.default_plan.experience) {
                <button class="secondary" type="button" [aria-pressed]="selected.experience === option.default_plan.experience"
                        [disabled]="starting()" (click)="chooseExperience(option.default_plan)">{{ option.name }}</button>
              }
            </div>
          </div>
          <p class="multi-photo-description">{{ creative()?.description ?? 'Choose how many photos to take and how to arrange them.' }}</p>
          @let counts = creative()?.counts ?? options.counts;
          @if (counts.length > 1) {
            <div class="multi-photo-field">
              <h3 id="photo-count-label">Number of photos</h3>
              <div class="multi-photo-counts" role="group" aria-labelledby="photo-count-label">
                @for (count of counts; track count) {
                  <button type="button" class="secondary" [aria-pressed]="count === selected.count" [disabled]="starting()"
                          (click)="chooseCount(count)">{{ count }}</button>
                }
              </div>
            </div>
          }
          @if (selected.experience === 'signature-strip') {
            <div class="multi-photo-field">
              <h3 id="photo-layout-label">Layout</h3>
              <div class="multi-photo-layouts" role="group" aria-labelledby="photo-layout-label">
                @for (option of options.layouts; track option.id) {
                  <button type="button" class="secondary multi-photo-layout" [aria-pressed]="option.id === selected.layout"
                          [disabled]="starting()" (click)="plan.set({ ...selected, layout: option.id })">
                    <app-composition-preview [geometry]="option" [count]="selected.count" [shape]="option.id" />
                    <span>{{ option.name }}</span>
                    <small>{{ option.size }}</small>
                  </button>
                }
              </div>
            </div>
          } @else if (creative(); as option) {
            @if (selected.experience === 'between-frames') {
              <label class="multi-photo-guidance">
                <input #guide type="checkbox" [checked]="selected.guided" [disabled]="starting()"
                       (change)="plan.set({ ...selected, guided: guide.checked })">
                Show pose prompts
              </label>
            }
            <div class="multi-photo-field multi-photo-example">
              <h3>Composition preview <span>{{ selected.experience === 'time-sculpture' ? '3 poses + 1 empty frame · ' : '' }}{{ option.composition.size }}</span></h3>
              <app-composition-preview [geometry]="option.composition" [count]="selected.count" [shape]="selected.experience" />
            </div>
          }
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
  readonly plan = signal<CapturePlan | null>(null);
  readonly creative = computed(() => this.catalog()?.creative?.find(option => option.default_plan.experience === this.plan()?.experience));
  readonly loading = signal(true);
  readonly starting = signal(false);
  readonly error = signal('');

  ngOnInit(): void { void this.load(); }

  chooseExperience(plan: CapturePlan): void {
    if (this.plan()?.experience !== plan.experience) this.plan.set(plan);
  }

  chooseCount(count: number): void {
    const selected = this.plan();
    if (selected && (selected.experience === 'signature-strip' || selected.experience === 'between-frames' ||
                    selected.experience === 'motion-study')) this.plan.set({ ...selected, count });
  }

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

  async start(plan: CapturePlan): Promise<void> {
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
