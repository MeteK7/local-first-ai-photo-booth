import { afterNextRender, Component, DestroyRef, ElementRef, inject } from '@angular/core';
import { I18n } from '../shared/i18n';

@Component({
  selector: 'button[appNewYearFrames]',
  host: {
    class: 'secondary new-year-frame-button',
    '[attr.aria-label]': "i18n.text('studio.newYearFrames')",
    '(click)': 'replayEntrance()',
  },
  template: `
    <span class="new-year-popper" aria-hidden="true"></span>
    <span class="new-year-button-copy">
      <span class="new-year-eyebrow" aria-hidden="true">{{ i18n.text('studio.newYearCelebrate') }} <span>2027</span></span>
      <span class="new-year-button-title">{{ i18n.text('studio.newYearFrames') }}</span>
    </span>
    <span class="new-year-chevron" aria-hidden="true"></span>
    <span class="new-year-confetti" aria-hidden="true">
      @for (piece of pieces; track piece) { <i></i> }
    </span>
    <span class="new-year-burst" aria-hidden="true">
      @for (piece of pieces; track piece) { <i [style.--piece-index]="piece"></i> }
    </span>
    <span class="new-year-glow-ring" aria-hidden="true"></span>
  `,
  styles: `
    :host(.new-year-frame-button) {
      --new-year-popper-size: 34px;
      --new-year-confetti-size: 24px;
      --new-year-confetti-overflow: 14px;
      position: relative; isolation: isolate; display: flex; align-items: center;
      gap: 12px; width: 100%; min-width: 0; min-height: 100px; margin-top: 6px;
      padding: 18px 15px 15px calc(var(--new-year-popper-size) - min(22px, var(--new-year-popper-size) * .28) + 23px);
      border: 1px solid #d17a83; border-radius: 9px; overflow: visible;
      color: #fff3f2; background: linear-gradient(120deg, #74313d, #4d2633);
      text-align: left; font: inherit; box-shadow: inset 0 0 0 1px #ea7d8512;
      transition: border-color 160ms, box-shadow 160ms;
    }
    :host(.new-year-frame-button)::before {
      content: ''; position: absolute; top: 0; left: 0; right: 0; height: 4px;
      border-radius: 8px 8px 0 0;
      background: repeating-linear-gradient(110deg, #f2ce8d 0 12px, #c65b65 12px 24px);
    }
    :host(.new-year-frame-button:hover:enabled) {
      background: linear-gradient(120deg, #803946, #5b2c3b); border-color: #f1b0a5;
      box-shadow: inset 0 0 0 1px #ea7d85, 0 0 20px #ea7d851a;
    }
    :host(.new-year-frame-button[aria-expanded="true"]),
    :host(.new-year-frame-button[aria-pressed="true"]),
    :host(.new-year-frame-button.studio-frame-active) {
      color: #fff3f2; background: linear-gradient(120deg, #843d49, #5a2b3a);
      border-color: #f5d391; box-shadow: inset 0 0 0 1px #f5d391;
    }
    .new-year-popper {
      position: absolute; left: max(-22px, var(--new-year-popper-size) * -.28); top: 50%;
      transform: translateY(-50%); width: var(--new-year-popper-size); height: var(--new-year-popper-size);
      background: #ffd5a1; mask: url('../../icons/party-popper.svg') center / contain no-repeat;
      pointer-events: none; z-index: 3;
    }
    .new-year-button-copy { position: relative; z-index: 1; display: grid; gap: 5px; flex: 1 1 0; min-width: 0; }
    .new-year-button-copy::before { content: ''; position: absolute; width: 1px; left: -14px; top: -3px; bottom: -3px; background: #c582817d; }
    .new-year-eyebrow { display: flex; align-items: center; flex-wrap: wrap; gap: 9px; color: #ffd7b4; font-size: 11px; font-weight: 600; line-height: 1.3; letter-spacing: .065em; text-transform: uppercase; }
    .new-year-eyebrow span { border-left: 1px solid #c58281; padding-left: 9px; color: #ffe6bc; font-size: 10px; line-height: 1; }
    .new-year-button-title { color: #fff3f2; font-size: 17px; font-weight: 650; line-height: 1.15; }
    .new-year-chevron { position: relative; z-index: 1; width: 7px; height: 7px; flex: 0 0 7px; margin-left: auto; color: #ffe4d5; border: solid currentColor; border-width: 0 2px 2px 0; transform: rotate(45deg); transition: transform 160ms; }
    :host([aria-expanded="true"]) .new-year-chevron { transform: rotate(225deg); }
    .new-year-confetti, .new-year-burst { position: absolute; inset: 0; pointer-events: none; z-index: 2; }
    .new-year-confetti i, .new-year-burst i { position: absolute; display: block; width: var(--new-year-confetti-size); height: calc(var(--new-year-confetti-size) * .42); background: #f5d391; border-radius: 1.5px; }
    .new-year-confetti i:nth-child(3n + 2), .new-year-burst i:nth-child(3n + 2) { background: #fa9aa4; }
    .new-year-confetti i:nth-child(3n), .new-year-burst i:nth-child(3n) { background: #99c8e9; }
    .new-year-confetti i:nth-child(1) { left: calc(-1 * var(--new-year-confetti-overflow)); top: 15%; transform: rotate(-32deg); }
    .new-year-confetti i:nth-child(2) { left: 15%; top: calc(-1 * var(--new-year-confetti-overflow)); transform: rotate(36deg); width: calc(var(--new-year-confetti-size) * .7); }
    .new-year-confetti i:nth-child(3) { left: 48%; top: -6px; transform: rotate(-16deg); }
    .new-year-confetti i:nth-child(4) { right: 8%; top: calc(-1 * var(--new-year-confetti-overflow)); transform: rotate(28deg); }
    .new-year-confetti i:nth-child(5) { right: calc(-1 * var(--new-year-confetti-overflow)); top: 37%; transform: rotate(61deg); }
    .new-year-confetti i:nth-child(6) { left: calc(-1 * var(--new-year-confetti-overflow)); bottom: 13%; transform: rotate(24deg); width: calc(var(--new-year-confetti-size) * .7); }
    .new-year-confetti i:nth-child(7) { right: 13%; bottom: -7px; transform: rotate(-31deg); }
    .new-year-confetti i:nth-child(8) { left: 28%; bottom: -8px; transform: rotate(31deg); width: calc(var(--new-year-confetti-size) * .65); }
    .new-year-burst i { left: 40px; top: 50%; opacity: 0; }
    .new-year-glow-ring { position: absolute; pointer-events: none; z-index: 0; inset: -3px; border: 2px solid #ffd7a0; border-radius: 12px; opacity: 0; }
    :host(.new-year-entering) { animation: new-year-arrival 960ms cubic-bezier(.2,.7,.3,1); }
    :host(.new-year-entering) .new-year-glow-ring { animation: new-year-arrival-halo 1450ms ease-out; }
    :host(.new-year-entering) .new-year-burst i { animation: new-year-paper-burst 1150ms cubic-bezier(.15,.6,.3,1) calc(var(--piece-index) * 24ms); }
    @keyframes new-year-arrival {
      0% { transform: scale(.97); box-shadow: 0 0 0 0 #ef8e9255; }
      28% { transform: scale(1.025); box-shadow: 0 0 22px 2px #f3a1a440; }
      60% { transform: scale(.995); box-shadow: 0 0 12px 0 #f3a1a425; }
      100% { transform: scale(1); box-shadow: 0 0 0 0 #ef8e9200; }
    }
    @keyframes new-year-arrival-halo {
      0% { opacity: 0; transform: scale(.985); }
      20% { opacity: .85; transform: scale(1.015); }
      60% { opacity: .35; transform: scale(1.065); }
      100% { opacity: 0; transform: scale(1.1); }
    }
    @keyframes new-year-paper-burst {
      0% { opacity: 0; transform: translate(0, 0) rotate(0deg) scale(.45); }
      25% { opacity: 1; transform: translate(calc(var(--burst-x) * .5), calc(var(--burst-y) * .5)) rotate(calc(var(--burst-angle) * .5)); }
      70% { opacity: .9; transform: translate(var(--burst-x), var(--burst-y)) rotate(var(--burst-angle)); }
      100% { opacity: 0; transform: translate(var(--burst-x), calc(var(--burst-y) + 8px)) rotate(calc(var(--burst-angle) + 35deg)) scale(.9); }
    }
    @media (prefers-reduced-motion: reduce) {
      :host(.new-year-frame-button), .new-year-chevron, .new-year-glow-ring, .new-year-burst i { animation: none !important; transition: none !important; }
    }
  `,
})
export class NewYearFramesButton {
  protected readonly i18n = inject(I18n);
  protected readonly pieces = [0, 1, 2, 3, 4, 5, 6, 7];
  private readonly element = inject<ElementRef<HTMLButtonElement>>(ElementRef);
  private observer?: IntersectionObserver;
  private cleanupTimer?: ReturnType<typeof setTimeout>;
  private replayFrame?: number;

  constructor() {
    const destroy = inject(DestroyRef);
    afterNextRender(() => {
      if (destroy.destroyed || typeof IntersectionObserver === 'undefined' || globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
      this.observer = new IntersectionObserver(entries => {
        if (!entries.some(entry => entry.isIntersecting && entry.intersectionRatio >= .5)) return;
        this.observer?.disconnect();
        this.playEntrance();
      }, { threshold: .5 });
      this.observer.observe(this.element.nativeElement);
    });
    destroy.onDestroy(() => {
      this.observer?.disconnect();
      clearTimeout(this.cleanupTimer);
      if (this.replayFrame !== undefined) cancelAnimationFrame(this.replayFrame);
    });
  }

  protected replayEntrance(): void {
    this.observer?.disconnect();
    if (this.replayFrame !== undefined) cancelAnimationFrame(this.replayFrame);
    // Wait for the gallery toggle to finish resizing the button before placing the burst.
    this.replayFrame = requestAnimationFrame(() => {
      this.replayFrame = undefined;
      this.playEntrance();
    });
  }

  private playEntrance(): void {
    const button = this.element.nativeElement;
    if (button.disabled || globalThis.matchMedia?.('(prefers-reduced-motion: reduce)').matches) return;
    clearTimeout(this.cleanupTimer);
    button.classList.remove('new-year-entering');
    // Restart even when a second click arrives before the previous animation ends.
    void button.offsetWidth;
    const width = button.clientWidth, height = button.clientHeight;
    const bleed = 21;
    const targets = [[-bleed, 7], [width * .18, -bleed], [width * .52, -bleed], [width * .83, -bleed],
      [width + bleed - 24, height * .3], [width * .79, height + bleed], [width * .3, height + bleed], [-bleed, height * .78]];
    button.querySelectorAll<HTMLElement>('.new-year-burst i').forEach((piece, index) => {
      piece.style.setProperty('--burst-x', `${targets[index][0] - 40}px`);
      piece.style.setProperty('--burst-y', `${targets[index][1] - height / 2}px`);
      piece.style.setProperty('--burst-angle', `${index * 71 - 100}deg`);
    });
    button.classList.add('new-year-entering');
    this.cleanupTimer = setTimeout(() => button.classList.remove('new-year-entering'), 1500);
  }
}
