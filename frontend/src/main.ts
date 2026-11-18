import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { Component } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { provideRouter, RouterLink, RouterOutlet } from '@angular/router';
import { Admin } from './app/admin/admin';
import { SessionPage } from './app/customer/session';
import { Welcome } from './app/customer/welcome';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  template: `
    <header class="site-header"><a class="brand" routerLink="/">
      <span class="brand-mark" aria-hidden="true"></span> LOCAL PHOTO BOOTH
    </a><a class="quiet-link" routerLink="/admin">Administration</a></header>
    <main id="content" class="shell"><router-outlet /></main>
  `,
})
class App {}

bootstrapApplication(App, {
  providers: [
    provideRouter([
      { path: '', component: Welcome },
      { path: 'session', component: SessionPage },
      { path: 'admin', component: Admin },
      { path: '**', redirectTo: '' },
    ]),
    provideHttpClient(withInterceptors([
      (request, next) => next(request.url.startsWith('/api/') && request.method !== 'GET'
        ? request.clone({ setHeaders: { 'X-Booth-Request': '1' } }) : request),
    ])),
  ],
}).catch(error => console.error(error));
