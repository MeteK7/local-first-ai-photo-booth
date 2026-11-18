import { Component, inject, input, OnDestroy, OnInit, signal } from '@angular/core';
import { Api, message, PhotoResultKind, PrintJob } from '../shared/api';

@Component({
  selector: 'app-photo-print',
  styles: [':host { display: contents; }'],
  template: `
    @if (!job() || job()?.state === 'failed') {
      <button type="button" class="secondary icon-action" [disabled]="disabled() || pending()" (click)="print()">
        <span class="action-icon print-icon" aria-hidden="true"></span>
        <span>
          @if (sending()) { Sending print… }
          @else if (kind() === 'effect') { {{ job() ? 'Retry effect print' : 'Print effect' }} }
          @else { {{ job() ? 'Retry print' : 'Print' }} }
        </span>
      </button>
    }
    @if (job(); as status) { <p class="print-status" role="status">{{ status.detail }}</p> }
    @if (error()) { <p class="print-status error" role="alert">{{ error() }}</p> }
  `,
})
export class PhotoPrintAction implements OnInit, OnDestroy {
  private readonly api = inject(Api);
  readonly assetId = input.required<string>();
  readonly kind = input.required<PhotoResultKind>();
  readonly disabled = input(false);
  readonly job = signal<PrintJob | null>(null);
  readonly error = signal('');
  readonly pending = signal(true);
  readonly sending = signal(false);
  private timer?: ReturnType<typeof setTimeout>;
  private destroyed = false;

  async ngOnInit(): Promise<void> {
    try {
      await this.refresh();
    } finally {
      this.pending.set(false);
    }
  }

  async print(): Promise<void> {
    if (this.pending() || this.disabled()) return;
    this.pending.set(true);
    this.sending.set(true);
    this.error.set('');
    try {
      this.job.set(await this.api.print(this.assetId(), this.kind()));
      this.watch();
    } catch (error) {
      this.error.set(message(error, 'Could not send the print. Try again to check the same job.'));
    } finally {
      this.pending.set(false);
      this.sending.set(false);
    }
  }

  private async refresh(): Promise<void> {
    try {
      this.job.set(await this.api.printStatus(this.assetId(), this.kind()));
      this.error.set('');
    } catch {
      this.error.set('Could not check the print status.');
    }
    this.watch();
  }

  private watch(): void {
    const state = this.job()?.state;
    if (!this.destroyed && (state === 'queued' || state === 'submitting' || state === 'submitted')) {
      this.timer = setTimeout(() => void this.refresh(), 1800);
    }
  }

  ngOnDestroy(): void {
    this.destroyed = true;
    clearTimeout(this.timer);
  }
}
