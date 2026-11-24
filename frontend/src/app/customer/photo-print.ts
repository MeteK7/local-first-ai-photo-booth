import { Component, inject, input, OnDestroy, OnInit, signal } from '@angular/core';
import { Api, message, PhotoResultKind, PrintJob } from '../shared/api';
import { I18n, UiMessage } from '../shared/i18n';

@Component({
  selector: 'app-photo-print',
  styles: [':host { display: contents; }'],
  template: `
    @if (!job() || job()?.state === 'failed') {
      <button type="button" class="secondary icon-action" [disabled]="disabled() || pending()" (click)="print()">
        <span class="action-icon print-icon" aria-hidden="true"></span>
        <span>
          @if (sending()) { {{ i18n.text('print.sending') }} }
          @else { {{ i18n.text(job() ? 'print.retry' : 'print.action') }} }
        </span>
      </button>
    }
    @if (job(); as status) { <p class="print-status" role="status">{{ i18n.detail(status.messages, status.detail, 'messages.print.' + status.state) }}</p> }
    @if (error(); as errors) { <p class="print-status error" role="alert">{{ i18n.notices(errors) }}</p> }
  `,
})
export class PhotoPrintAction implements OnInit, OnDestroy {
  protected readonly i18n = inject(I18n);
  private readonly api = inject(Api);
  readonly assetId = input.required<string>();
  readonly kind = input.required<PhotoResultKind>();
  readonly disabled = input(false);
  readonly job = signal<PrintJob | null>(null);
  readonly error = signal<UiMessage[] | null>(null);
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
    this.error.set(null);
    try {
      this.job.set(await this.api.print(this.assetId(), this.kind()));
      this.watch();
    } catch (error) {
      this.error.set(message(error, 'messages.printRequest'));
    } finally {
      this.pending.set(false);
      this.sending.set(false);
    }
  }

  private async refresh(): Promise<void> {
    try {
      this.job.set(await this.api.printStatus(this.assetId(), this.kind()));
      this.error.set(null);
    } catch {
      this.error.set([{ key: 'messages.printCheck' }]);
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
