import { Component, computed, inject, input, OnInit, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Api, CapturePlan, CompositionGeometry, message, MotionLayoutChoice, MultiPhotoCatalog, NewYearChoice, portraitFirst } from '../shared/api';
import { I18n, UiMessage } from '../shared/i18n';
import { NewYearFramesButton } from './new-year-frames-button';

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
  imports: [RouterLink, CompositionPreview, NewYearFramesButton],
  template: `
    <section class="panel multi-photo" aria-labelledby="multi-photo-title">
      <header class="multi-photo-header">
        <h1 id="multi-photo-title">{{ i18n.text('common.multi') }}</h1>
      </header>
      @if (catalog(); as options) {
        @if (plan(); as selected) {
          <div class="multi-photo-collections">
            @if (options.new_year?.length) {
              <div class="multi-photo-collection multi-new-year-collection" role="group" aria-labelledby="new-year-collection">
                <h2 id="new-year-collection">{{ i18n.text('studio.newYearCollection') }}</h2>
                <button appNewYearFrames class="studio-frame-toggle" type="button"
                        [aria-pressed]="selected.experience === 'new-year'" [attr.aria-expanded]="newYearOpen()"
                        aria-controls="multi-new-year-options" [disabled]="starting()" (click)="toggleNewYear()"></button>
              </div>
            }
            <div class="multi-photo-collection" role="group" aria-labelledby="classic-collection">
              <h2 id="classic-collection">{{ i18n.text('studio.classicCollection') }}</h2>
              <button class="secondary" type="button" [aria-pressed]="selected.experience === 'signature-strip'"
                      [disabled]="starting()" (click)="chooseExperience(options.default_plan)">{{ i18n.text('studio.experience.signature-strip.name') }}</button>
            </div>
            <div class="multi-photo-collection multi-photo-creative-modes" role="group" aria-labelledby="creative-collection">
              <h2 id="creative-collection">{{ i18n.text('studio.creativeCollection') }}</h2>
              @for (option of options.creative ?? []; track option.default_plan.experience) {
                <button class="secondary" type="button" [aria-pressed]="selected.experience === option.default_plan.experience"
                        [disabled]="starting()" (click)="chooseExperience(option.default_plan)">{{ i18n.text('studio.experience.' + option.default_plan.experience + '.name') }}</button>
              }
            </div>
          </div>
          @if (newYearOpen()) {
            <div id="multi-new-year-options" class="multi-new-year-options" role="group"
                 [attr.aria-label]="i18n.text('studio.newYearFrames')">
              @for (template of newYearOptions(); track template.id) {
                <button type="button" class="secondary multi-new-year-template"
                        [aria-pressed]="newYear()?.id === template.id" [disabled]="starting()"
                        (click)="chooseNewYear(template)">
                  <img [src]="template.preview" [attr.width]="template.preview_width ?? 480"
                       [attr.height]="template.preview_height ?? 720" alt="">
                  <span>{{ newYearName(template) }}</span>
                  <small>{{ i18n.text('studio.newYearPhotoCount', { count: template.default_plan.count }) }}</small>
                </button>
              }
            </div>
          }
          <p class="multi-photo-description">{{ description() }}</p>
          @let counts = newYear() ? [selected.count] : motionLayout()?.counts ?? creative()?.counts ?? options.counts;
          <div [class.motion-study-controls]="selected.experience === 'motion-study' && options.motion_layouts?.length">
            @if (selected.experience === 'motion-study' && options.motion_layouts?.length) {
              <div class="multi-photo-field">
                <h3 id="motion-layout-label">{{ i18n.text('studio.layout') }}</h3>
                <div class="multi-photo-layouts" role="group" aria-labelledby="motion-layout-label">
                  @for (layout of options.motion_layouts; track layout.id) {
                    <button type="button" class="secondary" [aria-pressed]="selected.layout === layout.id"
                            [disabled]="starting()" (click)="chooseMotionLayout(layout)">{{ motionName(layout) }}</button>
                  }
                </div>
              </div>
            }
            @if (counts.length > 1) {
              <div class="multi-photo-field">
                <h3 id="photo-count-label">{{ i18n.text('studio.photoCount') }}</h3>
                <div class="multi-photo-counts" role="group" aria-labelledby="photo-count-label">
                  @for (count of counts; track count) {
                    <button type="button" class="secondary" [aria-pressed]="count === selected.count" [disabled]="starting()"
                            (click)="chooseCount(count)">{{ i18n.number(count) }}</button>
                  }
                </div>
              </div>
            } @else if (motionLayout()) {
              <div class="multi-photo-field">
                <h3>{{ i18n.text('studio.photoCount') }}</h3>
                <p class="motion-study-fixed-count">{{ i18n.number(selected.count) }}</p>
              </div>
            }
          </div>
          @if (selected.experience === 'signature-strip') {
            <div class="multi-photo-field">
              <h3 id="photo-layout-label">{{ i18n.text('studio.layout') }}</h3>
              <div class="multi-photo-layouts" role="group" aria-labelledby="photo-layout-label">
                @for (option of options.layouts; track option.id) {
                  <button type="button" class="secondary multi-photo-layout" [aria-pressed]="option.id === selected.layout"
                          [disabled]="starting()" (click)="plan.set({ ...selected, layout: option.id })">
                    <app-composition-preview [geometry]="option" [count]="selected.count" [shape]="option.id" />
                    <span>{{ i18n.text('studio.layout.' + option.id) }}</span>
                    <small>{{ i18n.size(option.size) }}</small>
                  </button>
                }
              </div>
            </div>
          } @else if (newYear(); as template) {
            <div class="multi-photo-field multi-photo-example">
              <h3>{{ newYearName(template) }} <span>{{ i18n.size(template.size) }} ·
                {{ i18n.text('studio.newYearPhotoCount', { count: selected.count }) }}</span></h3>
              <div class="multi-photo-mat">
                <img class="multi-new-year-preview" [src]="template.preview" [attr.width]="template.preview_width ?? 480"
                     [attr.height]="template.preview_height ?? 720"
                     [style.--new-year-preview-width-ratio]="newYearPreviewWidthRatio()"
                     [alt]="i18n.text('studio.sampleAlt', { layout: newYearName(template), count: selected.count })">
              </div>
            </div>
          } @else if (creative(); as option) {
            @if (selected.experience === 'between-frames') {
              <label class="multi-photo-guidance">
                <input #guide type="checkbox" [checked]="selected.guided" [disabled]="starting()"
                       (change)="plan.set({ ...selected, guided: guide.checked })">
                {{ i18n.text('studio.guidance') }}
              </label>
            }
            <div class="multi-photo-field multi-photo-example">
              <h3>{{ i18n.text('studio.compositionPreview') }} <span>
                @let size = i18n.size(option.composition.size);
                {{ selected.experience === 'time-sculpture' ? i18n.text('studio.sculptureFrames', { size }) : size }}
              </span></h3>
              @if (motionLayout(); as layout) {
                <div class="multi-photo-mat">
                  <img class="motion-study-print-sample" [src]="sampleUrl(layout, selected.count)" width="720" height="480"
                       [alt]="i18n.text('studio.sampleAlt', { layout: motionName(layout), count: selected.count })">
                </div>
              } @else {
                <app-composition-preview [geometry]="option.composition" [count]="selected.count" [shape]="selected.experience" />
              }
            </div>
          }
          <div class="actions multi-photo-actions">
            <button type="button" class="primary" [disabled]="starting()" (click)="start(selected)">
              {{ i18n.text(starting() ? 'studio.opening' : 'studio.continue') }}
            </button>
            <a class="secondary" routerLink="/">{{ i18n.text('common.back') }}</a>
          </div>
        }
      } @else if (loading()) {
        <p role="status">{{ i18n.text('studio.loading') }}</p>
      } @else {
        <div class="actions">
          <button type="button" class="primary" (click)="load()">{{ i18n.text('common.tryAgain') }}</button>
          <a class="secondary" routerLink="/">{{ i18n.text('common.back') }}</a>
        </div>
      }
      @if (error(); as errors) { <p class="error" role="alert">{{ i18n.notices(errors) }}</p> }
    </section>
  `,
})
export class MultiPhotoStudio implements OnInit {
  protected readonly i18n = inject(I18n);
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  readonly catalog = signal<MultiPhotoCatalog | null>(null);
  readonly plan = signal<CapturePlan | null>(null);
  readonly newYearOpen = signal(false);
  protected readonly newYearOptions = computed(() => [...(this.catalog()?.new_year ?? [])].sort(portraitFirst));
  readonly newYear = computed(() => {
    const selected = this.plan();
    return selected?.experience === 'new-year'
      ? this.catalog()?.new_year?.find(template => template.id === selected.template) : undefined;
  });
  protected readonly newYearPreviewWidthRatio = computed(() => {
    const template = this.newYear();
    const width = template?.preview_width ?? 480;
    const height = template?.preview_height ?? 720;
    return width / Math.max(width, height);
  });
  readonly creative = computed(() => this.catalog()?.creative?.find(option => option.default_plan.experience === this.plan()?.experience));
  readonly motionLayout = computed(() => {
    const selected = this.plan();
    return selected?.experience === 'motion-study'
      ? this.catalog()?.motion_layouts?.find(layout => layout.id === selected.layout)
      : undefined;
  });
  readonly loading = signal(true);
  readonly starting = signal(false);
  readonly error = signal<UiMessage[] | null>(null);

  protected readonly description = computed(() => {
    const template = this.newYear();
    if (template) return this.i18n.text('studio.newYear.' + template.id + '.description');
    const motion = this.motionLayout();
    if (motion) return this.i18n.text('studio.motion.' + motion.id + '.description');
    const creative = this.creative();
    return this.i18n.text(creative
      ? 'studio.experience.' + creative.default_plan.experience + '.description' : 'studio.stripDescription');
  });

  protected motionName(layout: MotionLayoutChoice): string {
    return this.i18n.text('studio.motion.' + layout.id + '.name');
  }

  protected sampleUrl(layout: MotionLayoutChoice, count: number): string {
    const url = layout.previews[count];
    return this.i18n.locale() === 'tr' ? url + '?locale=tr' : url;
  }

  ngOnInit(): void { void this.load(); }

  chooseExperience(plan: CapturePlan): void {
    this.newYearOpen.set(false);
    if (this.plan()?.experience !== plan.experience) this.plan.set(plan);
  }

  toggleNewYear(): void {
    const open = !this.newYearOpen();
    const first = this.newYearOptions()[0];
    if (open && this.plan()?.experience !== 'new-year' && first) this.chooseNewYear(first);
    this.newYearOpen.set(open);
  }

  chooseNewYear(template: NewYearChoice): void { this.plan.set(template.default_plan); }

  protected newYearName(template: NewYearChoice): string {
    return this.i18n.text('studio.newYear.' + template.id + '.name');
  }

  chooseCount(count: number): void {
    const selected = this.plan();
    if (selected && (selected.experience === 'signature-strip' || selected.experience === 'between-frames' ||
                    selected.experience === 'motion-study')) this.plan.set({ ...selected, count });
  }

  chooseMotionLayout(layout: MotionLayoutChoice): void {
    const selected = this.plan();
    if (selected?.experience !== 'motion-study') return;
    this.plan.set({ ...selected, layout: layout.id, count: layout.counts.includes(selected.count) ? selected.count : layout.counts[0] });
  }

  async load(): Promise<void> {
    this.loading.set(true);
    this.error.set(null);
    try {
      if (await this.api.current()) {
        await this.router.navigateByUrl('/session', { replaceUrl: true });
        return;
      }
      const catalog = await this.api.multiPhotoCatalog();
      this.plan.set(catalog.default_plan);
      this.catalog.set(catalog);
    } catch (error) {
      this.error.set(message(error, 'messages.studioCatalog'));
    } finally {
      this.loading.set(false);
    }
  }

  async start(plan: CapturePlan): Promise<void> {
    if (this.starting()) return;
    this.starting.set(true);
    this.error.set(null);
    try {
      await this.api.start('filmstrip', plan);
      await this.router.navigateByUrl('/session');
    } catch (error) {
      this.error.set(message(error, 'messages.sessionOpen'));
    } finally {
      this.starting.set(false);
    }
  }
}
