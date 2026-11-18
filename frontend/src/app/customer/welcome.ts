import { Component, inject, signal } from '@angular/core';
import { Router } from '@angular/router';
import { Api, Experience, message } from '../shared/api';

@Component({
  selector: 'app-welcome',
  template: `
    <section class="welcome">
      <div class="welcome-copy">
        <h1>Your moment.<br>In focus.</h1>
        <p class="intro">Choose a single photo or a three-shot filmstrip.</p>
        <div class="actions">
          <button class="primary" type="button" [disabled]="busy()" (click)="start('single')">Single photo</button>
          <button class="secondary" type="button" [disabled]="busy()" (click)="start('filmstrip')">Classic filmstrip</button>
        </div>
        @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
      </div>
      <div class="lens-panel" aria-hidden="true"><div class="lens"></div></div>
    </section>
  `,
})
export class Welcome {
  private readonly api = inject(Api);
  private readonly router = inject(Router);
  readonly busy = signal(false);
  readonly error = signal('');

  async start(experience: Experience): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    try {
      await this.api.start(experience);
      await this.router.navigateByUrl('/session');
    } catch (error) {
      this.error.set(message(error, 'The booth is unavailable. Please try again.'));
    } finally {
      this.busy.set(false);
    }
  }
}
