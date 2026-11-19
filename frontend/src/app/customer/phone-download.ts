import { DatePipe } from '@angular/common';
import { Component, computed, inject, input, signal } from '@angular/core';
import { Api, message, PhoneLink, PhotoResultKind } from '../shared/api';

@Component({
  selector: 'app-phone-download',
  imports: [DatePipe],
  styles: [':host { display: contents; }'],
  template: `
    <button type="button" class="secondary icon-action" [disabled]="disabled() || pending()" (click)="createLink()">
      <span class="action-icon qr-icon" aria-hidden="true"></span>
      <span>
        @if (pending()) { Creating QR code… }
        @else { {{ link() ? 'New QR code' : 'Download on phone' }} }
      </span>
    </button>
    @if (link(); as phone) {
      <section class="phone-download" [attr.aria-label]="resultName() + ' phone download'">
        <img [src]="phone.qr_image" [alt]="'QR code for ' + resultName().toLowerCase()">
        <div>
          <strong>{{ resultName() }}</strong>
          <p>Connect to the same Wi-Fi as the booth, then scan the code with your phone camera.</p>
          <p>Expires at {{ phone.expires_at | date:'shortTime' }}.</p>
        </div>
      </section>
    }
    @if (error()) { <p class="phone-download-error error" role="alert">{{ error() }}</p> }
  `,
})
export class PhoneDownloadAction {
  private readonly api = inject(Api);
  readonly assetId = input.required<string>();
  readonly kind = input.required<PhotoResultKind>();
  readonly label = input('');
  readonly disabled = input(false);
  readonly link = signal<PhoneLink | null>(null);
  readonly pending = signal(false);
  readonly error = signal('');
  readonly resultName = computed(() => this.label() || ({
    original: 'Original photo', filmstrip: 'Signature Strip', effect: 'Processed photo', creative: 'Creative Studio photo',
  })[this.kind()]);

  async createLink(): Promise<void> {
    if (this.disabled() || this.pending()) return;
    this.pending.set(true);
    this.error.set('');
    try {
      this.link.set(await this.api.createPhoneLink(this.assetId(), this.kind()));
    } catch (error) {
      this.error.set(message(error, 'Could not create a phone download link.'));
    } finally {
      this.pending.set(false);
    }
  }
}
