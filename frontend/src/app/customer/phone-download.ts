import { Component, computed, inject, input, signal } from '@angular/core';
import { Api, message, PhoneLink, PhotoResultKind } from '../shared/api';
import { I18n, UiMessage } from '../shared/i18n';

@Component({
  selector: 'app-phone-download',
  styles: [':host { display: contents; }'],
  template: `
    <button type="button" class="secondary icon-action" [disabled]="disabled() || pending()" (click)="createLink()">
      <span class="action-icon qr-icon" aria-hidden="true"></span>
      <span>
        @if (pending()) { {{ i18n.text('phone.creating') }} }
        @else { {{ i18n.text(link() ? 'phone.newCode' : 'phone.action') }} }
      </span>
    </button>
    @if (link(); as phone) {
      <section class="phone-download" [attr.aria-label]="i18n.text('phone.section', { name: resultName() })">
        <img [src]="phone.qr_image" [alt]="i18n.text('phone.qrAlt', { name: resultName() })">
        <div>
          <strong>{{ resultName() }}</strong>
          <p>{{ i18n.text('phone.instructions') }}</p>
          <p>{{ i18n.text('phone.expiry', { time: i18n.date(phone.expires_at, 'short') }) }}</p>
        </div>
      </section>
    }
    @if (error(); as errors) { <p class="phone-download-error error" role="alert">{{ i18n.notices(errors) }}</p> }
  `,
})
export class PhoneDownloadAction {
  protected readonly i18n = inject(I18n);
  private readonly api = inject(Api);
  readonly assetId = input.required<string>();
  readonly kind = input.required<PhotoResultKind>();
  readonly label = input('');
  readonly disabled = input(false);
  readonly link = signal<PhoneLink | null>(null);
  readonly pending = signal(false);
  readonly error = signal<UiMessage[] | null>(null);
  readonly resultName = computed(() => this.label() || this.i18n.text({
    original: 'common.original', filmstrip: 'studio.experience.signature-strip.name',
    effect: 'studio.processed', creative: 'studio.creativePhoto',
  }[this.kind()]));

  async createLink(): Promise<void> {
    if (this.disabled() || this.pending()) return;
    this.pending.set(true);
    this.error.set(null);
    try {
      this.link.set(await this.api.createPhoneLink(this.assetId(), this.kind()));
    } catch (error) {
      this.error.set(message(error, 'messages.phoneRequest'));
    } finally {
      this.pending.set(false);
    }
  }
}
