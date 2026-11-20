import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, message, Overview } from '../shared/api';
import { I18n, UiMessage } from '../shared/i18n';

@Component({
  selector: 'app-admin',
  imports: [FormsModule],
  template: `
    <section class="panel">
      <div class="section-header"><h1>{{ i18n.text('common.admin') }}</h1>
        @if (overview()) { <button type="button" class="secondary" (click)="logout()" [disabled]="busy()">{{ i18n.text('admin.signOut') }}</button> }
      </div>
      @if (loading()) { <p role="status">{{ i18n.text('admin.checking') }}</p> }
      @else if (overview(); as data) {
        <dl class="status-grid">
          <div><dt>{{ i18n.text('admin.database') }}</dt><dd>{{ i18n.text('admin.state.' + data.database, undefined, i18n.text('admin.state.unknown')) }}</dd></div>
          <div><dt>{{ i18n.text('admin.camera') }}</dt><dd>{{ i18n.text('admin.state.' + data.camera, undefined, i18n.text('admin.state.unknown')) }}</dd></div>
          <div><dt>{{ i18n.text('admin.signedIn') }}</dt><dd>{{ data.username }}</dd></div>
        </dl>
        <h2>{{ i18n.text('admin.storage') }}</h2><p class="storage">{{ data.storage }}</p>
        <h2>{{ i18n.text('admin.recent') }}</h2>
        @if (data.sessions.length) {
          <div class="table-wrap"><table>
            <thead><tr><th scope="col">{{ i18n.text('admin.started') }}</th><th scope="col">{{ i18n.text('admin.status') }}</th><th scope="col">{{ i18n.text('admin.sessionId') }}</th></tr></thead>
            <tbody>
              @for (session of data.sessions; track session.id) {
                <tr><td>{{ i18n.date(session.started_at, 'medium') }}</td><td>{{ i18n.text('admin.state.' + displayState(session)) }}</td><td><code>{{ session.id }}</code></td></tr>
              }
            </tbody>
          </table></div>
        } @else { <p>{{ i18n.text('admin.noSessions') }}</p> }
      } @else {
        <form class="login" (ngSubmit)="login()">
          <label for="username">{{ i18n.text('admin.username') }}</label>
          <input id="username" name="username" autocomplete="username" [(ngModel)]="username" required maxlength="64">
          <label for="password">{{ i18n.text('admin.password') }}</label>
          <input id="password" name="password" type="password" autocomplete="current-password" [(ngModel)]="password" required maxlength="256">
          <button class="primary" type="submit" [disabled]="busy() || !username || !password">
            {{ i18n.text(busy() ? 'admin.signingIn' : 'admin.signIn') }}
          </button>
        </form>
      }
      @if (error(); as errors) { <p class="error" role="alert">{{ i18n.notices(errors) }}</p> }
    </section>
  `,
})
export class Admin implements OnInit {
  protected readonly i18n = inject(I18n);
  private readonly api = inject(Api);
  readonly overview = signal<Overview | null>(null);
  readonly error = signal<UiMessage[] | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  username = '';
  password = '';

  async ngOnInit(): Promise<void> {
    try {
      this.overview.set(await this.api.overview());
    } catch (error) {
      if (!(error instanceof HttpErrorResponse && error.status === 401)) {
        this.error.set(message(error, 'messages.adminCheck'));
      }
    } finally {
      this.loading.set(false);
    }
  }

  async login(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.login(this.username, this.password);
      this.overview.set(await this.api.overview());
    } catch (error) {
      this.error.set(message(error, 'messages.loginFailed'));
    } finally {
      this.password = '';
      this.busy.set(false);
    }
  }

  async logout(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.logout();
      this.overview.set(null);
    } catch (error) {
      this.error.set(message(error, 'messages.logoutFailed'));
    } finally {
      this.busy.set(false);
    }
  }

  displayState(session: Overview['sessions'][number]): string {
    return session.state === 'active' && Date.parse(session.expires_at) <= Date.now()
      ? 'expired' : session.state;
  }
}
