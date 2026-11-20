import { Component, computed, inject, OnDestroy, OnInit, signal, viewChild } from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { Api, CameraStatus, Composition, message, Photo, Session } from '../shared/api';
import { CreativeStudio } from './creative-studio';
import { PhotoPrintAction } from './photo-print';
import { PhoneDownloadAction } from './phone-download';
import { I18n, legacyKey, UiMessage } from '../shared/i18n';

@Component({
  selector: 'app-session',
  imports: [RouterLink, CreativeStudio, PhotoPrintAction, PhoneDownloadAction],
  template: `
    <section class="panel session" aria-labelledby="session-title">
      <header class="session-header">
        <h1 id="session-title">{{ i18n.text('session.title') }}</h1>
        @if (active()) {
          <p class="session-mode">{{ isFilmstrip() ? i18n.text('session.multiMode', { title: studioTitle() }) : i18n.text('common.single') }}</p>
        }
      </header>
      @if (loading()) { <p role="status">{{ i18n.text('session.checking') }}</p> }
      @else if (active()) {
        @if (photo(); as result) {
          @if (isFilmstrip()) {
            <section class="session-result" aria-labelledby="session-result-title">
              <h2 id="session-result-title">{{ i18n.text('session.result', { title: resultTitle() }) }}</h2>
              @if (fallbackReason(); as reason) {
                <p class="session-result-notice" role="status">{{ i18n.text('session.posesReady', { reason }) }}</p>
              }
              <div class="photo-stage">
                <img [src]="api.photoUrl(result, 'preview', 'filmstrip')"
                     [alt]="fallbackReason() ? i18n.text('session.poseAlt') : i18n.text('session.resultAlt', { title: studioTitle() })">
              </div>
              <div class="actions result-actions" role="group" [attr.aria-label]="i18n.text('session.resultActions')">
                <a class="primary icon-action" [href]="api.photoUrl(result, 'download', 'filmstrip')" download>
                  <span class="action-icon download-icon" aria-hidden="true"></span>
                  <span>{{ i18n.text('session.downloadComposition') }}</span>
                </a>
                <app-phone-download [assetId]="result.id" kind="filmstrip" [label]="resultTitle()" [disabled]="busy()" />
                <app-photo-print [assetId]="result.id" kind="filmstrip" [disabled]="busy()" />
              </div>
            </section>
          } @else {
            <app-creative-studio [photo]="result" [sessionBusy]="busy()" />
            <section class="ai-preview" aria-labelledby="ai-preview-heading">
              <h2 id="ai-preview-heading">{{ i18n.text('session.ai') }}</h2>
              <p>{{ i18n.text('session.soon') }}</p>
            </section>
          }
        } @else {
          <div class="session-capture">
            @if (isFilmstrip() && !filmstripComplete()) {
              <div class="session-progress-group" role="status" aria-atomic="true">
                <p class="session-progress">{{ i18n.text('session.progress', { current: shotsTaken() + 1, total: shotsRequired() }) }}</p>
                @if (shotPrompt(); as prompt) { <p class="session-shot-prompt">{{ prompt }}</p> }
              </div>
            }
            @if (filmstripComplete()) {
              <div class="camera-state" role="status">{{ busy() ? i18n.text('session.rendering') : i18n.count('session.allReady', shotsRequired()) }}</div>
              <button type="button" class="primary" [disabled]="busy()" (click)="retryFilmstrip()">{{ i18n.text('session.compose') }}</button>
            } @else {
              @if (frameUrl(); as frame) {
                <div class="photo-stage">
                  <div class="session-live-frame" [class.sculpture-framing]="isSculpture()">
                    <img [src]="frame" [alt]="i18n.text('session.liveAlt')">
                    @if (isSculpture() && shotsTaken()) {
                      <div class="sculpture-guides" aria-hidden="true">
                        @for (position of ['left', 'center', 'right']; track position) {
                          <span [class.active-guide]="$index + 1 === shotsTaken()">{{ i18n.text('studio.positions.' + position) }}</span>
                        }
                      </div>
                    }
                  </div>
                  @if (countdown(); as seconds) { <div class="countdown" role="status">{{ i18n.number(seconds) }}</div> }
                  @if (capturing()) { <div class="countdown progress" role="status">{{ transferMessage() }}</div> }
                </div>
              } @else {
                <div class="camera-state" role="status">{{ i18n.notices(cameraCaption()) }}</div>
              }
              <button type="button" class="primary icon-action capture-action"
                      [disabled]="busy() || !frameUrl() || camera()?.state !== 'ready'"
                      (click)="takePhoto()">
                <span class="shutter-disc" aria-hidden="true"><span class="action-icon shutter-icon"></span></span>
                <span>{{ captureLabel() }}</span>
              </button>
              @if (isFilmstrip() && !busy()) {
                <p class="session-capture-note">{{ introduction() }}</p>
              }
            }
          </div>
        }
        <footer class="session-end">
          @if (photo()) {
            <p class="session-end-note">{{ i18n.text('session.endNote') }}</p>
          }
          <div class="session-end-actions" role="group" [attr.aria-label]="i18n.text('session.endActions')">
            <button type="button" class="secondary session-cancel" [disabled]="busy() || sharing() || printing()"
                    (click)="finish('canceled')">{{ i18n.text('session.cancel') }}</button>
            <button type="button" class="secondary session-finish" [disabled]="busy() || sharing() || printing()"
                    (click)="finish('completed')">{{ i18n.text('session.finish') }}</button>
          </div>
        </footer>
      } @else {
        <p>{{ i18n.text(error() ? 'session.statusError' : 'messages.noSession') }}</p>
        <a class="secondary" routerLink="/">{{ i18n.text('common.back') }}</a>
      }
      @if (error(); as errors) { <p class="error" role="alert">{{ i18n.notices(errors) }}</p> }
    </section>
  `,
})
export class SessionPage implements OnInit, OnDestroy {
  protected readonly i18n = inject(I18n);
  protected readonly api = inject(Api);
  private readonly router = inject(Router);
  readonly active = signal<Session | null>(null);
  readonly loading = signal(true);
  readonly busy = signal(false);
  readonly error = signal<UiMessage[] | null>(null);
  readonly cameraCaption = signal<UiMessage[]>([{ key: 'session.checkingCamera' }]);
  readonly camera = signal<CameraStatus | null>(null);
  readonly frameUrl = signal<string | null>(null);
  readonly photo = signal<Photo | Composition | null>(null);
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
  readonly directions = computed(() => this.active()?.studio_directions);
  readonly studioTitle = computed(() => this.i18n.text(this.directions()?.title_key ??
    'studio.experience.' + (this.active()?.multi_photo_plan?.experience ?? 'signature-strip') + '.name'));
  readonly isSculpture = computed(() => this.active()?.multi_photo_plan?.experience === 'time-sculpture');
  readonly fallbackReason = computed(() => {
    const result = this.photo();
    return result && 'fallback_reason' in result && result.fallback_reason
      ? this.i18n.detail(result.messages, result.fallback_reason, 'messages.sculptureFallback') : null;
  });
  readonly resultTitle = computed(() => this.fallbackReason() ? this.i18n.text('session.poseSequence') : this.studioTitle());
  readonly captureLabel = computed(() => {
    if (this.isSculpture()) return this.i18n.text(this.shotsTaken() ? 'session.takePose' : 'session.takeEmpty');
    if (this.directions()?.manual_advance) return this.i18n.text(this.shotsTaken() ? 'session.takeNext' : 'session.takeFirst');
    if (this.isFilmstrip()) return this.shotsTaken()
      ? this.i18n.text('session.continueCapture') : this.i18n.text('session.takeCount', { count: this.shotsRequired() });
    return this.i18n.text('session.take');
  });
  readonly introduction = computed(() => {
    const directions = this.directions();
    return directions?.introduction_key ? this.i18n.text(directions.introduction_key)
      : directions?.introduction ?? this.i18n.text('session.countdownHint');
  });
  readonly shotPrompt = computed(() => {
    const directions = this.directions();
    const index = this.shotsTaken();
    return this.i18n.text(directions?.prompt_keys?.[index] ?? '', undefined, directions?.prompts[index]);
  });
  readonly transferMessage = computed(() => this.i18n.text(this.shotsTaken() + 1 < this.shotsRequired()
    ? this.directions()?.transfer_key ?? 'session.saving' : 'session.saving'));
  private stopped = false;
  private timer?: ReturnType<typeof setTimeout>;
  private cameraUpdate?: Promise<void>;
  private requestId?: string;

  async ngOnInit(): Promise<void> {
    try {
      this.active.set(await this.api.current());
    } catch (error) {
      this.error.set(message(error, 'messages.tryAgain'));
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
      this.error.set(message(error, 'messages.savedPhotoCheck'));
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
          this.cameraCaption.set([{ key: 'session.openingCamera' }]);
          const frame = await this.api.liveView();
          if (!this.stopped && !this.photo() && !this.capturing()) this.setFrame(URL.createObjectURL(frame));
          interval = 200;
        } else {
          this.setFrame(null);
          this.cameraCaption.set(camera?.messages?.length ? camera.messages
            : [{ key: legacyKey(camera?.detail) ?? 'messages.cameraUnavailable' }]);
        }
      } catch {
        this.camera.set(null);
        this.setFrame(null);
        this.cameraCaption.set([{ key: 'session.previewInterrupted' }]);
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
    this.error.set(null);
    try {
      while (this.shotsTaken() < this.shotsRequired()) {
        const captured = await this.captureOne();
        if (!captured || this.stopped) return;
        this.shotsTaken.update(count => count + 1);
        if (!this.isFilmstrip()) {
          this.photo.set(captured);
          return;
        }
        if (!this.filmstripComplete()) {
          if (this.directions()?.manual_advance) return;
          await this.waitForLiveView();
        }
      }
      await this.renderFilmstrip();
    } catch (error) {
      this.error.set(message(error, 'messages.captureFailed'));
    } finally {
      this.countdown.set(0);
      this.capturing.set(false);
      this.busy.set(false);
    }
  }

  private async captureOne(): Promise<Photo | undefined> {
    const directions = this.directions();
    const duration = (this.shotsTaken() ? directions?.next_countdown : directions?.first_countdown) ?? 3;
    for (let seconds = duration; seconds > 0; seconds--) {
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
    this.error.set(null);
    try {
      await this.renderFilmstrip();
    } catch (error) {
      this.error.set(message(error, 'messages.composeRetry'));
    } finally {
      this.busy.set(false);
    }
  }

  async finish(state: 'completed' | 'canceled'): Promise<void> {
    if (this.busy() || this.sharing() || this.printing()) return;
    this.busy.set(true);
    this.error.set(null);
    try {
      await this.api.finish(state);
      this.active.set(null);
      await this.router.navigateByUrl('/');
    } catch (error) {
      this.error.set(message(error, 'messages.finishFailed'));
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
