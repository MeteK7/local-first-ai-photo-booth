import { Component, computed, inject, input, OnDestroy, signal, viewChild } from '@angular/core';
import { Api, EffectOptions, message, PhotoFile } from '../shared/api';
import { PhotoPrintAction } from './photo-print';
import { PhoneDownloadAction } from './phone-download';

@Component({
  selector: 'app-ai-photo',
  imports: [PhotoPrintAction, PhoneDownloadAction],
  template: `
    <section class="ai-effect" aria-label="AI photo preview">
      <h2 class="effect-heading">
        <button class="secondary effect-toggle" type="button" aria-controls="effect-content"
                [attr.aria-expanded]="opened()" [disabled]="sessionBusy()" (click)="toggle()">
          AI photo preview
        </button>
      </h2>
      <div class="effect-content" id="effect-content" [hidden]="!opened()">
        @if (catalog(); as choices) {
          @if (choices.provider; as provider) {
            <h3>{{ provider.sends_photo ? 'AI photo effect' : 'Local test effect' }}</h3>
            @if (choices.templates.length > 1) {
              <label for="photo-effect">Choose an effect</label>
              <select id="photo-effect" #effect [value]="selected()" [disabled]="printing() || sharing()" (change)="choose(effect.value)">
                @for (template of choices.templates; track template.id) {
                  <option [value]="template.id">{{ template.name }}</option>
                }
              </select>
            }
            @if (template(); as effect) {
              <p class="effect-description"><strong>{{ effect.name }}</strong> · {{ effect.description }}</p>
              @if (effect.job; as job) {
                <p role="status">{{ job.detail }}</p>
                @if (job.state === 'completed') {
                  <div class="photo-stage">
                    <img [src]="api.effectUrl(job, 'preview')" alt="Your processed portrait">
                  </div>
                  <div class="actions result-actions" role="group" aria-label="Processed photo actions">
                    <a class="primary icon-action" [href]="api.effectUrl(job, 'download')" download="photo-booth-effect.jpg">
                      <span class="action-icon download-icon" aria-hidden="true"></span>
                      <span>Download effect</span>
                    </a>
                    @for (result of [job]; track result.id) {
                      <app-phone-download [assetId]="result.id" kind="effect" [disabled]="sessionBusy()" />
                      <app-photo-print [assetId]="result.id" kind="effect" [disabled]="sessionBusy()" />
                    }
                  </div>
                }
              }
              @if (!effect.job || effect.job.state === 'failed') {
                @if (provider.sends_photo && provider.privacy_url) {
                  <p><a [href]="provider.privacy_url" target="_blank" rel="noreferrer">Provider photo privacy policy</a></p>
                }
                <label class="effect-consent">
                  <input type="checkbox" #consentBox [checked]="consent()" (change)="consent.set(consentBox.checked)">
                  {{ provider.sends_photo
                    ? 'I agree to send this photo to ' + provider.label + ' to apply the effect.'
                    : 'I agree to use this photo for a test effect on this computer.' }}
                </label>
                <button class="primary" type="button" [disabled]="!consent() || busy() || sessionBusy()" (click)="apply()">
                  {{ provider.sends_photo ? 'Apply AI effect' : 'Create test image' }}
                </button>
              }
            } @else { <p role="status">There are no photo effects available.</p> }
          } @else { <p role="status">Photo effects are disabled on this booth.</p> }
        } @else if (opened() && !error()) { <p role="status">Loading photo effects…</p> }
        @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
        @if (error() && !catalog()) {
          <button type="button" class="secondary" (click)="refresh()">Try again</button>
        }
      </div>
    </section>
  `,
})
export class AiPhotoPanel implements OnDestroy {
  protected readonly api = inject(Api);
  readonly photo = input.required<PhotoFile>();
  readonly sessionBusy = input(false);
  readonly opened = signal(false);
  readonly catalog = signal<EffectOptions | null>(null);
  readonly selected = signal('');
  readonly consent = signal(false);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly template = computed(() => this.catalog()?.templates.find(effect => effect.id === this.selected()));
  private readonly printAction = viewChild(PhotoPrintAction);
  private readonly phoneDownload = viewChild(PhoneDownloadAction);
  readonly printing = computed(() => this.printAction()?.pending() ?? false);
  readonly sharing = computed(() => this.phoneDownload()?.pending() ?? false);
  private timer?: ReturnType<typeof setTimeout>;
  private requested = false;
  private destroyed = false;

  toggle(): void {
    this.opened.update(opened => !opened);
    if (this.opened() && !this.requested) {
      this.requested = true;
      void this.refresh();
    }
  }

  choose(id: string): void {
    this.selected.set(id);
    this.consent.set(false);
  }

  async refresh(): Promise<void> {
    try {
      const catalog = await this.api.effects(this.photo());
      this.catalog.set(catalog);
      if (!this.template()) this.choose(catalog.templates[0]?.id ?? '');
      this.error.set('');
    } catch (error) {
      this.error.set(message(error, 'Could not check the photo effect.'));
    }
    this.watch();
  }

  async apply(): Promise<void> {
    const effect = this.template();
    if (!effect || !this.consent() || this.busy()) return;
    clearTimeout(this.timer);
    this.busy.set(true);
    this.error.set('');
    try {
      const job = await this.api.applyEffect(this.photo(), effect.id, this.consent());
      this.catalog.update(catalog => catalog && ({
        ...catalog, templates: catalog.templates.map(item => item.id === effect.id ? { ...item, job } : item),
      }));
      this.consent.set(false);
    } catch (error) {
      this.error.set(message(error, 'Could not start the effect. Your original is available.'));
    } finally {
      this.busy.set(false);
      this.watch();
    }
  }

  private watch(): void {
    clearTimeout(this.timer);
    if (!this.destroyed && this.catalog()?.templates.some(
      effect => effect.job?.state === 'queued' || effect.job?.state === 'processing',
    )) {
      this.timer = setTimeout(() => void this.refresh(), 1000);
    }
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    clearTimeout(this.timer);
  }
}
