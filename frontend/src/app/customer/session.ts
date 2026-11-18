import { DatePipe } from '@angular/common';
import { Component, computed, inject, OnDestroy, OnInit, signal } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Api, CameraStatus, message, PhoneLink, Photo, PhotoFile, PrintJob, Session } from '../shared/api';
import { AiPhotoPanel } from './ai-photo';

@Component({
  selector: 'app-session',
  imports: [RouterLink, DatePipe, AiPhotoPanel],
  template: `
    <section class="panel session">
      <h1>Your session</h1>
      @if (loading()) { <p role="status">Checking your session…</p> }
      @else if (active()) {
        @if (isFilmstrip() && !photo() && !filmstripComplete()) {
          <p role="status">Photo {{ shotsTaken() + 1 }} of {{ shotsRequired() }}</p>
        }
        @if (photo(); as result) {
          <div class="photo-stage">
            <img [src]="api.photoUrl(result, 'preview', experience())"
                 [alt]="isFilmstrip() ? 'Your Classic filmstrip' : 'Your captured photo'">
          </div>
        } @else if (filmstripComplete()) {
          <div class="camera-state" role="status">{{ busy() ? 'Creating your filmstrip…' : 'Your three photos are ready.' }}</div>
        } @else if (frameUrl(); as frame) {
          <div class="photo-stage">
            <img [src]="frame" alt="Live view from the booth camera">
            @if (countdown(); as seconds) { <div class="countdown" role="status">{{ seconds }}</div> }
            @if (capturing()) { <div class="countdown progress" role="status">Saving your photo…</div> }
          </div>
        } @else {
          <div class="camera-state" role="status">{{ cameraCaption() }}</div>
        }
        <div class="actions">
          @if (photo(); as result) {
            <a class="primary" [href]="api.photoUrl(result, 'download', experience())"
               [attr.download]="isFilmstrip() ? 'classic-filmstrip.jpg' : 'photo-booth.jpg'">
              {{ isFilmstrip() ? 'Download filmstrip' : 'Download photo' }}
            </a>
            <button type="button" class="secondary" [disabled]="busy() || sharing()" (click)="downloadOnPhone(result)">
              {{ sharing() ? 'Creating QR code…' : phoneLink() ? 'New QR code' : 'Download on phone' }}
            </button>
            @if (!printJob() || printJob()?.state === 'failed') {
              <button type="button" class="secondary" [disabled]="busy() || printing()" (click)="printResult(result)">
                {{ printing() ? 'Sending print…' : printJob() ? 'Retry print' : 'Print' }}
              </button>
            }
          } @else if (filmstripComplete()) {
            <button type="button" class="primary" [disabled]="busy()" (click)="retryFilmstrip()">Create filmstrip</button>
          } @else {
            <button type="button" class="primary" [disabled]="busy() || !frameUrl() || camera()?.state !== 'ready'"
                    (click)="takePhoto()">
              {{ isFilmstrip() ? (shotsTaken() ? 'Continue filmstrip' : 'Take three photos') : 'Take photo' }}
            </button>
          }
          <button type="button" class="secondary" [disabled]="busy() || sharing() || printing()" (click)="finish('completed')">Finish session</button>
          <button type="button" class="secondary" [disabled]="busy() || sharing() || printing()" (click)="finish('canceled')">Cancel</button>
        </div>
        @if (printJob(); as job) { <p class="print-status" role="status">{{ job.detail }}</p> }
        @if (printError()) { <p class="error" role="alert">{{ printError() }}</p> }
        @if (phoneLink(); as link) {
          <section class="phone-download" aria-label="Phone download">
            <img [src]="link.qr_image" alt="QR code to download this photo on your phone">
            <div>
              <p>Connect to the same Wi-Fi as the booth, then scan the code with your phone camera.</p>
              <p>Expires at {{ link.expires_at | date:'shortTime' }}.</p>
            </div>
          </section>
        }
        @if (photo(); as source) {
          @if (!isFilmstrip()) { <app-ai-photo [photo]="source" /> }
        }
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
  readonly phoneLink = signal<PhoneLink | null>(null);
  readonly sharing = signal(false);
  readonly printJob = signal<PrintJob | null>(null);
  readonly printing = signal(false);
  readonly printError = signal('');
  readonly countdown = signal(0);
  readonly capturing = signal(false);
  readonly shotsTaken = signal(0);
  readonly shotsRequired = signal(1);
  readonly experience = computed(() => this.active()?.experience ?? 'single');
  readonly isFilmstrip = computed(() => this.experience() === 'filmstrip');
  readonly filmstripComplete = computed(() => this.isFilmstrip() && this.shotsTaken() === this.shotsRequired());
  private stopped = false;
  private timer?: ReturnType<typeof setTimeout>;
  private printTimer?: ReturnType<typeof setTimeout>;
  private cameraUpdate?: Promise<void>;
  private requestId?: string;

  async ngOnInit(): Promise<void> {
    try {
      this.active.set(await this.api.current());
    } catch (error) {
      this.error.set(message(error, 'Please try again.'));
    } finally {
      this.loading.set(false);
    }
    if (!this.active() || this.stopped) return;
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
    }
    if (!this.photo()) {
      if (this.filmstripComplete()) await this.retryFilmstrip();
      else this.startCameraUpdate();
    } else {
      this.printing.set(true);
      try {
        await this.refreshPrint(this.photo()!);
      } finally {
        this.printing.set(false);
      }
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
      const captured = await this.api.capture(this.requestId);
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
      throw new Error('Camera preview is still reconnecting. Continue the filmstrip once it returns.');
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
      this.error.set(message(error, 'Could not create the filmstrip. Your originals are saved.'));
    } finally {
      this.busy.set(false);
    }
  }

  async downloadOnPhone(result: PhotoFile): Promise<void> {
    if (this.busy() || this.sharing()) return;
    this.sharing.set(true);
    this.error.set('');
    try {
      this.phoneLink.set(await this.api.createPhoneLink(result, this.experience()));
    } catch (error) {
      this.error.set(message(error, 'Could not create a phone download link.'));
    } finally {
      this.sharing.set(false);
    }
  }

  async printResult(photo: PhotoFile): Promise<void> {
    if (this.printing() || this.busy()) return;
    this.printing.set(true);
    this.printError.set('');
    try {
      this.printJob.set(await this.api.print(photo, this.experience()));
      this.watchPrint(photo);
    } catch (error) {
      this.printError.set(message(error, 'Could not send the print. Try again to check the same job.'));
    } finally {
      this.printing.set(false);
    }
  }

  private async refreshPrint(photo: PhotoFile): Promise<void> {
    try {
      this.printJob.set(await this.api.printStatus(photo, this.experience()));
      this.printError.set('');
    } catch {
      this.printError.set('Could not check the print status.');
    }
    this.watchPrint(photo);
  }

  private watchPrint(photo: PhotoFile): void {
    const state = this.printJob()?.state;
    if (!this.stopped && this.active() && (state === 'queued' || state === 'submitting' || state === 'submitted')) {
      this.printTimer = setTimeout(() => void this.refreshPrint(photo), 1800);
    }
  }

  async finish(state: 'completed' | 'canceled'): Promise<void> {
    if (this.busy() || this.sharing() || this.printing()) return;
    this.busy.set(true);
    this.error.set('');
    try {
      await this.api.finish(state);
      this.active.set(null);
      this.phoneLink.set(null);
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
    clearTimeout(this.printTimer);
    this.setFrame(null);
  }
}
