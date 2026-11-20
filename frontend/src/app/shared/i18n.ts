import { DOCUMENT, effect, inject, Injectable, signal } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';
import en from '../../../../i18n/en.json';
import tr from '../../../../i18n/tr.json';

export const languages = [
  { code: 'en', name: 'English', format: 'en-US' },
  { code: 'tr', name: 'Türkçe', format: 'tr-TR' },
] as const;
export type Locale = typeof languages[number]['code'];
type Scope = 'kiosk' | 'admin';
type Params = Record<string, string | number>;

export interface UiMessage {
  key: string;
  params?: Params | null;
}

const catalogs: Record<Locale, Record<string, string>> = { en, tr };
const legacyKeys = new Map(Object.entries(en)
  .filter(([key]) => key.startsWith('messages.'))
  .map(([key, text]) => [text, key]));

export function legacyKey(text?: string | null): string | undefined {
  return text ? legacyKeys.get(text) : undefined;
}

export function isUiMessage(value: unknown): value is UiMessage {
  if (!value || typeof value !== 'object' || !('key' in value) ||
      typeof value.key !== 'string' || !Object.hasOwn(en, value.key)) return false;
  if (!('params' in value) || value.params == null) return true;
  return !!value.params && typeof value.params === 'object' &&
    Object.values(value.params).every(param => typeof param === 'number' || typeof param === 'string');
}

@Injectable({ providedIn: 'root' })
export class I18n {
  private readonly document = inject(DOCUMENT);
  private readonly translate = inject(TranslateService);
  private readonly preferences = { kiosk: this.read('kiosk'), admin: this.read('admin') };
  private scope: Scope = 'kiosk';
  private readonly active = signal(this.preferences.kiosk);
  readonly locale = this.active.asReadonly();

  constructor() {
    for (const { code } of languages) this.translate.setTranslation(code, catalogs[code]);
    effect(() => {
      this.document.documentElement.lang = this.locale();
      this.document.title = this.text('common.brand');
    });
  }

  enter(scope: Scope): void {
    this.scope = scope;
    this.active.set(this.preferences[scope]);
  }

  select(locale: Locale): void {
    this.active.set(locale);
    this.preferences[this.scope] = locale;
    try {
      this.document.defaultView?.localStorage.setItem(this.storageKey(this.scope), locale);
    } catch {
      // A restricted browser can still switch for the lifetime of the application.
    }
  }

  text(key: string, params?: Params, fallback?: string): string {
    const locale = this.locale();
    if (!Object.hasOwn(en, key)) return fallback ?? '';
    const formatted = params && Object.fromEntries(Object.entries(params).map(([name, value]) =>
      [name, typeof value === 'number' ? this.number(value) : value]));
    return this.translate.instant(key, formatted, locale) as string;
  }

  notices(messages: UiMessage[]): string {
    return messages.filter(isUiMessage).map(({ key, params }) => this.text(key, params ?? undefined)).join(' ');
  }

  detail(messages: UiMessage[] | undefined, legacy: string | null | undefined, fallback: string): string {
    if (messages?.some(isUiMessage)) return this.notices(messages);
    return this.text(legacyKey(legacy) ?? fallback);
  }

  number(value: number): string {
    return new Intl.NumberFormat(this.formatLocale()).format(value);
  }

  count(key: string, count: number): string {
    const category = new Intl.PluralRules(this.formatLocale()).select(count);
    const variant = `${key}.${category}`;
    return this.text(Object.hasOwn(en, variant) ? variant : `${key}.other`, { count });
  }

  date(value: string, style: 'short' | 'medium'): string {
    return new Intl.DateTimeFormat(this.formatLocale(), {
      timeStyle: style, ...(style === 'medium' ? { dateStyle: 'medium' } : {}),
    }).format(new Date(value));
  }

  size(value: string): string {
    const match = /^(\d+) × (\d+) in$/.exec(value);
    return match ? this.text('common.size', { width: Number(match[1]), height: Number(match[2]) }) : value;
  }

  private formatLocale(): string {
    return languages.find(({ code }) => code === this.locale())!.format;
  }

  private read(scope: Scope): Locale {
    try {
      const stored = this.document.defaultView?.localStorage.getItem(this.storageKey(scope));
      return languages.find(({ code }) => code === stored)?.code ?? 'en';
    } catch {
      return 'en';
    }
  }

  private storageKey(scope: Scope): string { return `photo-booth.language.${scope}`; }
}
