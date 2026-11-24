import { provideHttpClient, withInterceptors } from '@angular/common/http';
import { Location } from '@angular/common';
import { Component, inject } from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { bootstrapApplication } from '@angular/platform-browser';
import { NavigationEnd, provideRouter, Router, RouterLink, RouterOutlet } from '@angular/router';
import { provideTranslateService } from '@ngx-translate/core';
import { filter } from 'rxjs';
import { Admin } from './app/admin/admin';
import { MultiPhotoStudio } from './app/customer/multi-photo-studio';
import { SessionPage } from './app/customer/session';
import { Welcome } from './app/customer/welcome';
import { I18n, languages } from './app/shared/i18n';

@Component({
  selector: 'app-root',
  imports: [RouterOutlet, RouterLink],
  template: `
    <header class="site-header">
      <a class="brand" routerLink="/">
        <span class="brand-mark" aria-hidden="true"></span>{{ i18n.text('common.brandHeading') }}
      </a>
      <div class="site-tools">
        <div class="language-switch" role="group" [attr.aria-label]="i18n.text('common.language')">
          @for (language of languages; track language.code) {
            <button type="button" [attr.lang]="language.code" [attr.aria-pressed]="i18n.locale() === language.code"
                    (click)="i18n.select(language.code)">{{ language.name }}</button>
          }
        </div>
        <a class="quiet-link" routerLink="/admin">{{ i18n.text('common.admin') }}</a>
      </div>
    </header>
    <main id="content" class="shell"><router-outlet /></main>
  `,
})
class App {
  protected readonly i18n = inject(I18n);
  protected readonly languages = languages;

  constructor() {
    this.useRouteLanguage(inject(Location).path());
    inject(Router).events.pipe(
      filter(event => event instanceof NavigationEnd),
      takeUntilDestroyed(),
    ).subscribe(event => this.useRouteLanguage(event.urlAfterRedirects));
  }

  private useRouteLanguage(url: string): void {
    this.i18n.enter(url.split(/[?#]/, 1)[0].replace(/\/$/, '') === '/admin' ? 'admin' : 'kiosk');
  }
}

bootstrapApplication(App, {
  providers: [
    provideTranslateService(),
    provideRouter([
      { path: '', component: Welcome },
      { path: 'multi-photo-studio', component: MultiPhotoStudio },
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
