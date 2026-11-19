import { HttpClient, HttpErrorResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { firstValueFrom } from 'rxjs';

export interface Session {
  id: string;
  state: 'active' | 'completed' | 'canceled';
  experience: Experience;
  multi_photo_plan?: CapturePlan | null;
  studio_directions?: CaptureDirections | null;
  started_at: string;
  expires_at: string;
  ended_at: string | null;
}

export type Experience = 'single' | 'filmstrip';

export type StripLayout = 'vertical' | 'horizontal' | 'grid';

export interface SignatureStripPlan {
  experience: 'signature-strip';
  version: 1;
  count: number;
  layout: StripLayout;
}

export interface BetweenFramesPlan {
  experience: 'between-frames';
  version: 1;
  count: number;
  guided: boolean;
}

export interface MotionStudyPlan {
  experience: 'motion-study';
  version: 1;
  count: number;
  layout?: MotionStudyLayout;
}

export type MotionStudyLayout = 'contact-stack' | 'match-cut' | 'ascending-cut';

export interface MotionLayoutChoice {
  id: MotionStudyLayout;
  name: string;
  description: string;
  counts: number[];
  previews: Record<number, string>;
}

export interface StoryPlan {
  experience: 'mini-scene' | 'time-sculpture';
  version: 1;
  count: 4;
}

export type CreativePlan = BetweenFramesPlan | MotionStudyPlan | StoryPlan;
export type CapturePlan = SignatureStripPlan | CreativePlan;

export interface CaptureDirections {
  title: string;
  introduction: string;
  prompts: string[];
  first_countdown: number;
  next_countdown: number;
  transfer_note: string | null;
  manual_advance?: boolean;
}

export interface CompositionGeometry {
  size: string;
  width: number;
  height: number;
  frames: Record<number, [number, number, number, number][]>;
}

export interface MultiPhotoCatalog {
  default_plan: SignatureStripPlan;
  counts: number[];
  layouts: (CompositionGeometry & { id: StripLayout; name: string })[];
  motion_layouts?: MotionLayoutChoice[];
  creative?: {
    default_plan: CreativePlan;
    name: string;
    description: string;
    counts: number[];
    composition: CompositionGeometry;
  }[];
}

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

export interface Composition extends PhotoFile {
  fallback_reason?: string;
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

export type PhotoResultKind = 'original' | 'filmstrip' | 'effect' | 'creative';

export interface CreativeResult {
  id: string;
  kind: 'creative' | 'effect';
  state: 'queued' | 'processing' | 'completed' | 'failed' | 'canceled';
  detail: string;
}

export interface CreativeTreatment {
  id: string;
  name: string;
  description: string;
  result: CreativeResult | null;
}

interface FilmstripProgress {
  captured: number;
  required: number;
  result: Composition | null;
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

  start(experience: Experience, multiPhotoPlan?: CapturePlan) {
    return firstValueFrom(this.http.post<Session>('/api/sessions', {
      experience, multi_photo_plan: multiPhotoPlan,
    }));
  }
  multiPhotoCatalog() {
    return firstValueFrom(this.http.get<MultiPhotoCatalog>('/api/sessions/multi-photo-studio'));
  }
  current() { return firstValueFrom(this.http.get<Session | null>('/api/sessions/current')); }
  finish(state: 'completed' | 'canceled') {
    return firstValueFrom(this.http.post<Session>('/api/sessions/current/finish', { state }));
  }
  camera() { return firstValueFrom(this.http.get<CameraStatus>('/api/camera/status')); }
  liveView() { return firstValueFrom(this.http.get(`${photos}/live-view`, { responseType: 'blob' })); }
  latestPhoto() { return firstValueFrom(this.http.get<Photo | null>(`${photos}/latest`)); }
  capture(requestId: string, slot?: number) {
    return firstValueFrom(this.http.post<Photo>(photos, { request_id: requestId, slot }));
  }
  filmstrip() { return firstValueFrom(this.http.get<FilmstripProgress>(`${photos}/filmstrip`)); }
  composeFilmstrip() { return firstValueFrom(this.http.post<Composition>(`${photos}/filmstrip`, {})); }
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
  studio(photo: PhotoFile) {
    return firstValueFrom(this.http.get<CreativeTreatment[]>(`${photos}/creative`, { params: { asset_id: photo.id } }));
  }
  applyTreatment(photo: PhotoFile, treatment: string) {
    return firstValueFrom(this.http.post<CreativeResult>(`${photos}/creative`, {
      asset_id: photo.id, treatment,
    }));
  }
  creativeUrl(result: CreativeResult, action: 'preview' | 'download') {
    const route = result.kind === 'effect' ? 'ai' : 'creative';
    return `${photos}/${route}/${result.id}/${action}`;
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
