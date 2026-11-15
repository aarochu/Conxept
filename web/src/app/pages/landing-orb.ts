import { Component } from '@angular/core';

@Component({
  selector: 'app-landing-orb',
  template: `
    <div class="orb">
      <div class="orb-glow"></div>
      <div class="orb-shine"></div>
      <div class="orb-label">
        <span class="spinner"></span>
        Checking derivations…
      </div>
    </div>
  `,
  styles: `
    .orb {
      position: relative;
      width: min(440px, 80vw);
      aspect-ratio: 1;
      border-radius: 50%;
      overflow: hidden;
      background:
        radial-gradient(
          120% 70% at 50% 108%,
          #fff3d6 0%,
          #ff9a3c 14%,
          #b3361a 26%,
          #1a0c12 42%,
          transparent 58%
        ),
        radial-gradient(90% 60% at 50% 72%, #05060a 0%, #05060a 40%, transparent 70%),
        linear-gradient(180deg, #2b3566 0%, #49557f 38%, #7b7f98 55%, #3a3f5c 75%, #0b0d16 100%);
      box-shadow:
        inset 0 0 0 1px #ffffff30,
        inset 0 -24px 60px #ff8a3d40,
        inset 0 30px 80px #0b0f2a,
        0 40px 120px -20px #ff7a2a33;
    }
    .orb-glow {
      position: absolute;
      inset: -20%;
      background: conic-gradient(from 0deg, #ff8a3d00, #ff8a3d55, #6b7cff40, #ff8a3d00 70%);
      filter: blur(40px);
      mix-blend-mode: screen;
      opacity: 0.55;
    }
    .orb-shine {
      position: absolute;
      left: 18%;
      top: 8%;
      width: 64%;
      height: 34%;
      border-radius: 50%;
      background: radial-gradient(closest-side, #ffffff55, #ffffff00);
      filter: blur(6px);
    }
    .orb-label {
      position: absolute;
      inset: 0;
      display: grid;
      place-content: center;
      justify-items: center;
      gap: 10px;
      font-size: 0.85rem;
      color: #ffffffd9;
      transform: translateY(-14%);
    }
    .spinner {
      width: 16px;
      height: 16px;
      border-radius: 50%;
      border: 2px dotted #ffffffcc;
    }

    @media (max-width: 820px) {
      .orb {
        width: min(320px, 76vw);
      }
    }
  `,
})
export class LandingOrb {}
