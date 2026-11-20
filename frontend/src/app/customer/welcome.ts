import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Api, message } from '../shared/api';
import { I18n, UiMessage } from '../shared/i18n';

@Component({
  selector: 'app-welcome',
  imports: [RouterLink],
  template: `
    <section class="welcome">
      <div class="welcome-copy">
        <h1>{{ i18n.text('welcome.headlineStart') }}<br>{{ i18n.text('welcome.headlineEnd') }}</h1>
        <p class="intro">{{ i18n.text('welcome.intro') }}</p>
        <div class="actions">
          <button class="primary" type="button" [disabled]="busy()" (click)="startSingle()">{{ i18n.text('common.single') }}</button>
          <a class="secondary" routerLink="/multi-photo-studio">{{ i18n.text('common.multi') }}</a>
        </div>
        @if (error(); as errors) { <p class="error" role="alert">{{ i18n.notices(errors) }}</p> }
      </div>
      <div class="lens-panel" aria-hidden="true"><div class="lens"></div></div>
    </section>
  `,
})
export class Welcome {
  protected readonly i18n = inject(I18n);
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  readonly busy = signal(false);
  readonly error = signal<UiMessage[] | null>(null);

  async startSingle(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.start('single');
      await this.router.navigateByUrl('/session');
    } catch (error) {
      this.error.set(message(error, 'messages.boothUnavailable'));
    } finally {
      this.busy.set(false);
    }
  }
}
