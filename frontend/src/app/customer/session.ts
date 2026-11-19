import { Component, computed, inject, OnDestroy, OnInit, signal, viewChild } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Api, CameraStatus, message, Photo, PhotoFile, Session } from '../shared/api';
import { CreativeStudio } from './creative-studio';
import { PhotoPrintAction } from './photo-print';
import { PhoneDownloadAction } from './phone-download';

@Component({
  selector: 'app-session',
  imports: [RouterLink, CreativeStudio, PhotoPrintAction, PhoneDownloadAction],
  template: `
    <section class="panel session" aria-labelledby="session-title">
      <header class="session-header">
        <h1 id="session-title">Your session</h1>
        @if (active()) {
          <p class="session-mode">{{ isFilmstrip() ? 'Multi-Photo Studio · Signature Strip' : 'Single photo' }}</p>
        }
      </header>
      @if (loading()) { <p role="status">Checking your session…</p> }
      @else if (active()) {
        @if (photo(); as result) {
          @if (isFilmstrip()) {
            <section class="session-result" aria-labelledby="session-result-title">
              <h2 id="session-result-title">Your Signature Strip</h2>
              <div class="photo-stage">
                <img [src]="api.photoUrl(result, 'preview', 'filmstrip')" alt="Your Signature Strip composition">
              </div>
              <div class="actions result-actions" role="group" aria-label="Composition actions">
                <a class="primary icon-action" [href]="api.photoUrl(result, 'download', 'filmstrip')" download>
                  <span class="action-icon download-icon" aria-hidden="true"></span>
                  <span>Download composition</span>
                </a>
                <app-phone-download [assetId]="result.id" kind="filmstrip" [disabled]="busy()" />
                <app-photo-print [assetId]="result.id" kind="filmstrip" [disabled]="busy()" />
              </div>
            </section>
          } @else {
            <app-creative-studio [photo]="result" [sessionBusy]="busy()" />
            <section class="ai-preview" aria-labelledby="ai-preview-heading">
              <h2 id="ai-preview-heading">AI Preview</h2>
              <p>Coming Soon</p>
            </section>
          }
        } @else {
          <div class="session-capture">
            @if (isFilmstrip() && !filmstripComplete()) {
              <p class="session-progress" role="status">Photo {{ shotsTaken() + 1 }} of {{ shotsRequired() }}</p>
            }
            @if (filmstripComplete()) {
              <div class="camera-state" role="status">{{ busy() ? 'Creating your composition…' : 'All ' + shotsRequired() + ' photos are ready.' }}</div>
              <button type="button" class="primary" [disabled]="busy()" (click)="retryFilmstrip()">Create composition</button>
            } @else {
              @if (frameUrl(); as frame) {
                <div class="photo-stage">
                  <img [src]="frame" alt="Live view from the booth camera">
                  @if (countdown(); as seconds) { <div class="countdown" role="status">{{ seconds }}</div> }
                  @if (capturing()) { <div class="countdown progress" role="status">Saving your photo…</div> }
                </div>
              } @else {
                <div class="camera-state" role="status">{{ cameraCaption() }}</div>
              }
              <button type="button" class="primary icon-action capture-action"
                      [disabled]="busy() || !frameUrl() || camera()?.state !== 'ready'"
                      (click)="takePhoto()">
                <span class="shutter-disc" aria-hidden="true"><span class="action-icon shutter-icon"></span></span>
                <span>{{ isFilmstrip() ? (shotsTaken() ? 'Continue capture' : 'Take ' + shotsRequired() + ' photos') : 'Take photo' }}</span>
              </button>
              @if (isFilmstrip() && !busy()) {
                <p class="session-capture-note">The camera counts down before each photo.</p>
              }
            }
          </div>
        }
        <footer class="session-end">
          @if (photo()) {
            <p class="session-end-note">Finishing keeps QR links active until they expire. Canceling revokes them immediately.</p>
          }
          <div class="session-end-actions" role="group" aria-label="End your session">
            <button type="button" class="secondary session-cancel" [disabled]="busy() || sharing() || printing()"
                    (click)="finish('canceled')">Cancel session</button>
            <button type="button" class="secondary session-finish" [disabled]="busy() || sharing() || printing()"
                    (click)="finish('completed')">Finish session</button>
          </div>
        </footer>
      } @else {
        <p>{{ error() ? 'Session status could not be loaded.' : 'There is no active session.' }}</p>
        <a class="secondary" routerLink="/">Back to welcome</a>
      }
      @if (error()) { <p class="error" role="alert">{{ error() }}</p> }
    </section>
  `,
})
export class SessionPage implements OnInit, OnDestroy {
  protected readonly api = inject(Api);
  private readonly router = inject(Router);
  readonly active = signal<Session | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal('');
  readonly cameraCaption = signal('Checking camera availability…');
  readonly camera = signal<CameraStatus | null>(null);
  readonly frameUrl = signal<string | null>(null);
  readonly photo = signal<PhotoFile | null>(null);
  private readonly printAction = viewChild(PhotoPrintAction);
  private readonly phoneDownload = viewChild(PhoneDownloadAction);
  private readonly studio = viewChild(CreativeStudio);
  readonly printing = computed(() => this.printAction()?.pending() || this.studio()?.printing() || false);
  readonly sharing = computed(() => this.phoneDownload()?.pending() || this.studio()?.sharing() || false);
  readonly countdown = signal(0);
  readonly capturing = signal(false);
  readonly shotsTaken = signal(0);
  readonly shotsRequired = signal(1);
  readonly experience = computed(() => this.active()?.experience ?? 'single');
  readonly isFilmstrip = computed(() => this.experience() === 'filmstrip');
  readonly filmstripComplete = computed(() => this.isFilmstrip() && this.shotsTaken() === this.shotsRequired());
  private stopped = false;
  private timer?: ReturnType<typeof setTimeout>;
  private cameraUpdate?: Promise<void>;
  private requestId?: string;

  async ngOnInit(): Promise<void> {
    try {
      this.active.set(await this.api.current());
    } catch (error) {
      this.error.set(message(error, 'Please try again.'));
      this.loading.set(false);
      return;
    }
    if (!this.active() || this.stopped) {
      this.loading.set(false);
      return;
    }
    try {
      if (this.isFilmstrip()) {
        const progress = await this.api.filmstrip();
        this.shotsRequired.set(progress.required);
        this.shotsTaken.set(progress.captured);
        this.photo.set(progress.result);
      } else {
        this.photo.set(await this.api.latestPhoto());
      }
    } catch (error) {
      this.error.set(message(error, 'Could not check your saved photo. Reload to try again.'));
      return;
    } finally {
      this.loading.set(false);
    }
    if (!this.stopped && !this.photo()) {
      if (this.filmstripComplete()) await this.retryFilmstrip();
      else this.startCameraUpdate();
    }
  }

  private startCameraUpdate(): void {
    this.cameraUpdate = this.refreshCamera();
  }

  private async refreshCamera(): Promise<void> {
    if (this.stopped || !this.active() || this.photo() || this.filmstripComplete()) return;
    let interval = 1400;
    if (!this.capturing()) {
      try {
        if (this.camera()?.state !== 'ready') this.camera.set(await this.api.camera());
        const camera = this.camera();
        if (camera?.state === 'ready' && camera.live_view) {
          this.cameraCaption.set('Opening live view…');
          const frame = await this.api.liveView();
          if (!this.stopped && !this.photo() && !this.capturing()) this.setFrame(URL.createObjectURL(frame));
          interval = 200;
        } else {
          this.setFrame(null);
          this.cameraCaption.set(camera?.detail ?? 'Camera unavailable');
        }
      } catch {
        this.camera.set(null);
        this.setFrame(null);
        this.cameraCaption.set('Camera preview interrupted. Reconnecting…');
      }
    }
    if (!this.stopped && this.active() && !this.photo() && !this.filmstripComplete()) {
      this.timer = setTimeout(() => this.startCameraUpdate(), interval);
    }
  }

  private setFrame(url: string | null): void {
    const previous = this.frameUrl();
    this.frameUrl.set(url);
    if (previous) URL.revokeObjectURL(previous);
  }

  async takePhoto(): Promise<void> {
    if (this.busy() || !this.frameUrl() || this.camera()?.state !== 'ready') return;
    this.busy.set(true);
    this.error.set('');
    try {
      while (this.shotsTaken() < this.shotsRequired()) {
        const captured = await this.captureOne();
        if (!captured || this.stopped) return;
        this.shotsTaken.update(count => count + 1);
        if (!this.isFilmstrip()) {
          this.photo.set(captured);
          return;
        }
        if (!this.filmstripComplete()) await this.waitForLiveView();
      }
      await this.renderFilmstrip();
    } catch (error) {
      this.error.set(message(error, 'Could not take the photo. Please try again.'));
    } finally {
      this.countdown.set(0);
      this.capturing.set(false);
      this.busy.set(false);
    }
  }

  private async captureOne(): Promise<Photo | undefined> {
    for (let seconds = 3; seconds > 0; seconds--) {
      this.countdown.set(seconds);
      await new Promise(resolve => setTimeout(resolve, 1000));
      if (this.stopped) return;
    }
    this.countdown.set(0);
    this.capturing.set(true);
    try {
      await this.cameraUpdate;
      if (this.stopped) return;
      this.requestId ??= crypto.randomUUID();
      const slot = this.isFilmstrip() ? this.shotsTaken() + 1 : undefined;
      const captured = await this.api.capture(this.requestId, slot);
      this.requestId = undefined;
      this.setFrame(null);
      return captured;
    } finally {
      this.capturing.set(false);
    }
  }

  private async waitForLiveView(): Promise<void> {
    const deadline = Date.now() + 8000;
    while (!this.stopped && !this.frameUrl() && Date.now() < deadline) {
      await new Promise(resolve => setTimeout(resolve, 150));
    }
    if (!this.stopped && !this.frameUrl()) {
      throw new Error('Camera preview is still reconnecting. Continue capture once it returns.');
    }
  }

  private async renderFilmstrip(): Promise<void> {
    if (!this.stopped) this.photo.set(await this.api.composeFilmstrip());
  }

  async retryFilmstrip(): Promise<void> {
    if (this.busy()) return;
    this.busy.set(true);
    this.error.set('');
    try {
      await this.renderFilmstrip();
    } catch (error) {
      this.error.set(message(error, 'Could not create the composition. Your originals are saved.'));
    } finally {
      this.busy.set(false);
    }
  }

  async finish(state: 'completed' | 'canceled'): Promise<void> {
    if (this.busy() || this.sharing() || this.printing()) return;
    this.busy.set(true);
    this.error.set('');
    try {
      await this.api.finish(state);
      this.active.set(null);
      await this.router.navigateByUrl('/');
    } catch (error) {
      this.error.set(message(error, 'Could not end the session. Please try again.'));
    } finally {
      this.busy.set(false);
    }
  }

  ngOnDestroy(): void {
    this.stopped = true;
    clearTimeout(this.timer);
    this.setFrame(null);
  }
}
