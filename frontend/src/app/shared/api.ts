import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface Session {
  id: string;
  state: 'active' | 'completed' | 'canceled';
  experience: Experience;
  started_at: string;
  expires_at: string;
  ended_at: string | null;
}

export type Experience = 'single' | 'filmstrip';

export interface Overview {
  username: string;
  database: string;
  camera: string;
  storage: string;
  sessions: Session[];
}

export interface CameraStatus {
  state: 'unavailable' | 'ready' | 'busy' | 'blocked';
  model?: string;
  battery_percent?: number;
  live_view: boolean;
  capture: boolean;
  detail?: string;
}

export interface PhotoFile {
  id: string;
  byte_size: number;
  width: number;
  height: number;
}

export interface Photo extends PhotoFile {
  captured_at: string;
}

export interface PhoneLink {
  url: string;
  qr_image: string;
  expires_at: string;
}

export interface PrintJob {
  id: string;
  state: 'queued' | 'submitting' | 'submitted' | 'sent' | 'failed' | 'unknown';
  detail: string;
}

export type PhotoResultKind = 'original' | 'filmstrip' | 'effect';

export interface EffectJob {
  id: string;
  template_id: string;
  state: 'queued' | 'processing' | 'completed' | 'failed' | 'interrupted' | 'canceled';
  detail: string;
}

export interface PhotoEffect {
  id: string;
  name: string;
  description: string;
  job: EffectJob | null;
}

export interface EffectOptions {
  provider: { label: string; sends_photo: boolean; privacy_url: string | null } | null;
  templates: PhotoEffect[];
}

interface FilmstripProgress {
  captured: number;
  required: number;
  result: PhotoFile | null;
}

const photos = '/api/sessions/current/photos';

export function message(error: unknown, fallback: string): string {
  if (error instanceof HttpErrorResponse && typeof error.error?.detail === 'string') {
    return error.error.detail;
  }
  return fallback;
}

@Injectable({ providedIn: 'root' })
export class Api {
  private readonly http = inject(HttpClient);

  start(experience: Experience) {
    return firstValueFrom(this.http.post<Session>('/api/sessions', { experience }));
  }
  current() { return firstValueFrom(this.http.get<Session | null>('/api/sessions/current')); }
  finish(state: 'completed' | 'canceled') {
    return firstValueFrom(this.http.post<Session>('/api/sessions/current/finish', { state }));
  }
  camera() { return firstValueFrom(this.http.get<CameraStatus>('/api/camera/status')); }
  liveView() { return firstValueFrom(this.http.get(`${photos}/live-view`, { responseType: 'blob' })); }
  latestPhoto() { return firstValueFrom(this.http.get<Photo | null>(`${photos}/latest`)); }
  capture(requestId: string) {
    return firstValueFrom(this.http.post<Photo>(photos, { request_id: requestId }));
  }
  filmstrip() { return firstValueFrom(this.http.get<FilmstripProgress>(`${photos}/filmstrip`)); }
  composeFilmstrip() { return firstValueFrom(this.http.post<PhotoFile>(`${photos}/filmstrip`, {})); }
  createPhoneLink(assetId: string, kind: PhotoResultKind) {
    return firstValueFrom(this.http.post<PhoneLink>(`${photos}/phone-links`, {
      asset_id: assetId, kind,
    }));
  }
  printStatus(assetId: string, kind: PhotoResultKind) {
    const params = { asset_id: assetId, kind };
    return firstValueFrom(this.http.get<PrintJob | null>(`${photos}/print-jobs`, { params }));
  }
  print(assetId: string, kind: PhotoResultKind) {
    return firstValueFrom(this.http.post<PrintJob>(`${photos}/print-jobs`, {
      asset_id: assetId, kind,
    }));
  }
  effects(photo: PhotoFile) {
    return firstValueFrom(this.http.get<EffectOptions>(`${photos}/ai`, { params: { asset_id: photo.id } }));
  }
  applyEffect(photo: PhotoFile, templateId: string, consent: boolean) {
    return firstValueFrom(this.http.post<EffectJob>(`${photos}/ai`, {
      asset_id: photo.id, template_id: templateId, consent,
    }));
  }
  effectUrl(job: EffectJob, action: 'preview' | 'download') {
    return `${photos}/ai/${job.id}/${action}`;
  }
  photoUrl(photo: PhotoFile, action: 'preview' | 'download', experience: Experience) {
    const base = experience === 'filmstrip' ? `${photos}/filmstrip` : photos;
    return `${base}/${photo.id}/${action}`;
  }
  overview() { return firstValueFrom(this.http.get<Overview>('/api/admin/overview')); }
  login(username: string, password: string) {
    return firstValueFrom(this.http.post('/api/admin/login', { username, password }));
  }
  logout() { return firstValueFrom(this.http.post('/api/admin/logout', {})); }
}
