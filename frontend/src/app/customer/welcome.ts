import { Component, inject, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Api, message } from '../shared/api';

@Component({
  selector: 'app-welcome',
  imports: [RouterLink],
  template: `
    <section class="welcome">
      <div class="welcome-copy">
        <h1>Your moment.<br>In focus.</h1>
        <p class="intro">Take a single photo or capture a series in Multi-Photo Studio.</p>
        <div class="actions">
          <button class="primary" type="button" [disabled]="busy()" (click)="startSingle()">Single photo</button>
          <a class="secondary" routerLink="/multi-photo-studio">Multi-Photo Studio</a>
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

  async startSingle(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    try {
      await this.api.start('single');
      await this.router.navigateByUrl('/session');
    } catch (error) {
      this.error.set(message(error, 'The booth is unavailable. Please try again.'));
    } finally {
      this.busy.set(false);
    }
  }
}
