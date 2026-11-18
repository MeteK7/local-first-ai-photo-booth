import { DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, inject, OnInit, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Api, message, Overview } from '../shared/api';

@Component({
  selector: 'app-admin',
  imports: [FormsModule, DatePipe],
  template: `
    <section class="panel">
      <div class="section-header"><h1>Administration</h1>
        @if (overview()) { <button type="button" class="secondary" (click)="logout()" [disabled]="busy()">Sign out</button> }
      </div>
      @if (loading()) { <p role="status">Checking access…</p> }
      @else if (overview(); as data) {
        <dl class="status-grid">
          <div><dt>Database</dt><dd>{{ data.database }}</dd></div>
          <div><dt>Camera</dt><dd>{{ data.camera }}</dd></div>
          <div><dt>Signed in as</dt><dd>{{ data.username }}</dd></div>
        </dl>
        <h2>Storage</h2><p class="storage">{{ data.storage }}</p>
        <h2>Recent sessions</h2>
        @if (data.sessions.length) {
          <div class="table-wrap"><table>
            <thead><tr><th scope="col">Started</th><th scope="col">Status</th><th scope="col">Session ID</th></tr></thead>
            <tbody>
              @for (session of data.sessions; track session.id) {
                <tr><td>{{ session.started_at | date:'medium' }}</td><td>{{ displayState(session) }}</td><td><code>{{ session.id }}</code></td></tr>
              }
            </tbody>
          </table></div>
        } @else { <p>No sessions recorded yet.</p> }
      } @else {
        <form class="login" (ngSubmit)="login()">
          <label for="username">Username</label>
          <input id="username" name="username" autocomplete="username" [(ngModel)]="username" required maxlength="64">
          <label for="password">Password</label>
          <input id="password" name="password" type="password" autocomplete="current-password" [(ngModel)]="password" required maxlength="256">
          <button class="primary" type="submit" [disabled]="busy() || !username || !password">
            {{ busy() ? 'Signing in…' : 'Sign in' }}
          </button>
        </form>
      }
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    </section>
  `,
})
export class Admin implements OnInit {
  private readonly api = inject(Api);
  readonly overview = signal<Overview | null>(null);
  readonly error = signal('');
  readonly loading = signal(true);
  readonly busy = signal(false);
  username = '';
  password = '';

  async ngOnInit(): Promise<void> {
    try {
      this.overview.set(await this.api.overview());
    } catch (error) {
      if (!(error instanceof HttpErrorResponse && error.status === 401)) {
        this.error.set(message(error, 'Could not check administration access.'));
      }
    } finally {
      this.loading.set(false);
    }
  }

  async login(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    try {
      await this.api.login(this.username, this.password);
      this.overview.set(await this.api.overview());
    } catch (error) {
      this.error.set(message(error, 'Could not sign in.'));
    } finally {
      this.password = '';
      this.busy.set(false);
    }
  }

  async logout(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    try {
      await this.api.logout();
      this.overview.set(null);
    } catch (error) {
      this.error.set(message(error, 'Could not sign out.'));
    } finally {
      this.busy.set(false);
    }
  }

  displayState(session: Overview['sessions'][number]): string {
    return session.state === 'active' && Date.parse(session.expires_at) <= Date.now()
      ? 'expired' : session.state;
  }
}
