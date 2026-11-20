import { Component, computed, inject, input, OnDestroy, OnInit, signal, viewChild } from '@angular/core';
import { Api, CreativeTreatment, message, PhotoFile, PhotoResultKind } from '../shared/api';
import { PhoneDownloadAction } from './phone-download';
import { PhotoPrintAction } from './photo-print';
import { I18n, UiMessage } from '../shared/i18n';

interface DisplayPhoto {
  id: string;
  kind: PhotoResultKind;
  name: string;
  preview: string;
  download: string;
  filename: string;
}

@Component({
  selector: 'app-creative-studio',
  imports: [PhoneDownloadAction, PhotoPrintAction],
  template: `
    <section class="session-result studio" aria-labelledby="studio-heading">
      <h2 id="studio-heading">{{ i18n.text('studio.creativeTitle') }}</h2>
      <div class="studio-treatments" role="group" [attr.aria-label]="i18n.text('studio.treatments')">
        <button type="button" class="secondary" [attr.aria-pressed]="selected() === 'original'"
                [disabled]="deliveryPending() || sessionBusy()" (click)="selectOriginal()">{{ i18n.text('studio.original') }}</button>
        @for (item of treatments(); track item.id) {
          <button type="button" class="secondary" [attr.aria-pressed]="selected() === item.id"
                  [disabled]="deliveryPending() || sessionBusy()" (click)="choose(item)">
            {{ treatmentName(item) }}
          </button>
        }
      </div>
      @if (catalogError(); as errors) {
        <p class="error" role="alert">{{ i18n.notices(errors) }}</p>
        <button type="button" class="secondary" (click)="refresh()">{{ i18n.text('studio.reloadTreatments') }}</button>
      }
      @if (treatment(); as effect) {
        <div class="studio-caption">
          <h3>{{ treatmentName(effect) }}</h3>
          <p>{{ i18n.text('studio.treatment.' + effect.id + '.description', undefined, effect.description) }}</p>
        </div>
      }
      @if (display(); as photo) {
        <div class="photo-stage">
          <img [src]="photo.preview" [alt]="photo.name">
        </div>
        @for (asset of [photo]; track asset.kind + ':' + asset.id) {
          <div class="actions result-actions" role="group" [attr.aria-label]="i18n.text('studio.assetActions', { name: asset.name })">
            <a class="primary icon-action" [href]="asset.download" [attr.download]="asset.filename">
              <span class="action-icon download-icon" aria-hidden="true"></span>
              <span>{{ i18n.text('studio.download') }}</span>
            </a>
            <app-phone-download [assetId]="asset.id" [kind]="asset.kind" [label]="asset.name" [disabled]="sessionBusy()" />
            <app-photo-print [assetId]="asset.id" [kind]="asset.kind" [disabled]="sessionBusy()" />
          </div>
        }
      } @else if (treatment(); as effect) {
        <div class="camera-state studio-status">
          @if (requestErrors()[effect.id]; as error) {
            <p class="error" role="alert">{{ i18n.notices(error) }}</p>
          } @else {
            <p role="status">{{ requesting().has(effect.id) ? i18n.text('messages.creative.processing') : resultStatus(effect) }}</p>
          }
          @if (requestErrors()[effect.id] || effect.result?.state === 'failed') {
            <button type="button" class="secondary" [disabled]="requesting().has(effect.id) || sessionBusy()"
                    (click)="choose(effect)">{{ i18n.text('common.tryAgain') }}</button>
          }
        </div>
      }
    </section>
  `,
})
export class CreativeStudio implements OnInit, OnDestroy {
  protected readonly i18n = inject(I18n);
  private readonly api = inject(Api);
  readonly photo = input.required<PhotoFile>();
  readonly sessionBusy = input(false);
  readonly treatments = signal<CreativeTreatment[]>([]);
  readonly selected = signal('original');
  readonly catalogError = signal<UiMessage[] | null>(null);
  readonly requesting = signal<ReadonlySet<string>>(new Set());
  readonly requestErrors = signal<Partial<Record<string, UiMessage[]>>>({});
  private readonly print = viewChild(PhotoPrintAction);
  private readonly phone = viewChild(PhoneDownloadAction);
  readonly printing = computed(() => this.print()?.pending() ?? false);
  readonly sharing = computed(() => this.phone()?.pending() ?? false);
  readonly deliveryPending = computed(() => this.printing() || this.sharing());
  readonly treatment = computed(() => this.treatments().find(item => item.id === this.selected()));
  readonly display = computed<DisplayPhoto | null>(() => {
    if (this.selected() === 'original') {
      const photo = this.photo();
      return {
        id: photo.id, kind: 'original', name: this.i18n.text('common.original'), filename: 'photo-booth.jpg',
        preview: this.api.photoUrl(photo, 'preview', 'single'),
        download: this.api.photoUrl(photo, 'download', 'single'),
      };
    }
    const treatment = this.treatment();
    const result = treatment?.result;
    if (!treatment || result?.state !== 'completed') return null;
    return {
      id: result.id, kind: result.kind, name: this.treatmentName(treatment), filename: treatment.id + '.jpg',
      preview: this.api.creativeUrl(result, 'preview'), download: this.api.creativeUrl(result, 'download'),
    };
  });
  private timer?: ReturnType<typeof setTimeout>;
  private destroyed = false;
  private refreshing = false;
  private revision = 0;

  ngOnInit(): void { void this.refresh(); }

  selectOriginal(): void {
    if (!this.sessionBusy() && !this.deliveryPending()) this.selected.set('original');
  }

  async choose(item: CreativeTreatment): Promise<void> {
    if (this.sessionBusy() || this.deliveryPending()) return;
    this.selected.set(item.id);
    if (this.requesting().has(item.id) || (item.result && item.result.state !== 'failed')) return;
    this.requestErrors.update(errors => ({ ...errors, [item.id]: undefined }));
    this.requesting.update(pending => new Set([...pending, item.id]));
    try {
      const result = await this.api.applyTreatment(this.photo(), item.id);
      ++this.revision;
      this.treatments.update(items => items.map(treatment =>
        treatment.id === item.id ? { ...treatment, result } : treatment));
    } catch (error) {
      this.requestErrors.update(errors => ({
        ...errors, [item.id]: message(error, 'messages.treatmentRequest'),
      }));
    } finally {
      this.requesting.update(pending => new Set([...pending].filter(id => id !== item.id)));
      this.watch();
    }
  }

  async refresh(): Promise<void> {
    if (this.destroyed || this.refreshing) return;
    this.refreshing = true;
    const revision = this.revision;
    try {
      const treatments = await this.api.studio(this.photo());
      // A catalog response from before a successful POST must not replace the new result.
      if (revision === this.revision) this.treatments.set(treatments);
      this.catalogError.set(null);
      this.requestErrors.update(errors => Object.fromEntries(
        Object.entries(errors).filter(([id, error]) =>
          error && !treatments.some(item => item.id === id && item.result)),
      ));
    } catch (error) {
      this.catalogError.set(message(error, 'messages.treatmentCatalog'));
    } finally {
      this.refreshing = false;
      this.watch();
    }
  }

  protected treatmentName(treatment: CreativeTreatment): string {
    return this.i18n.text('studio.treatment.' + treatment.id + '.name', undefined, treatment.name);
  }

  protected resultStatus(treatment: CreativeTreatment): string {
    const result = treatment.result;
    return result ? this.i18n.detail(result.messages, result.detail, 'messages.creative.' + result.state) : '';
  }

  private watch(): void {
    clearTimeout(this.timer);
    if (!this.destroyed && this.treatments().some(item =>
      item.result?.state === 'queued' || item.result?.state === 'processing')) {
      this.timer = setTimeout(() => void this.refresh(), 1000);
    }
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    clearTimeout(this.timer);
  }
}
