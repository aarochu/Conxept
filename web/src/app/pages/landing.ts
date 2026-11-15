import { Component, DestroyRef, ElementRef, afterNextRender, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import {
  animate,
  createScope,
  onScroll,
  stagger,
  utils,
  type JSAnimation,
  type Scope,
} from 'animejs';

import { Latex } from '../latex';

/** One cell per derivation in the seeded demo class (60 students x 8 problems, seed 7). */
const GROUPS = [
  { key: 'valid', label: 'Every step valid', count: 167 },
  { key: 'named', label: 'Named misconception', count: 235 },
  { key: 'other', label: 'Other: outside the catalog', count: 78 },
] as const;
const TOTAL = GROUPS.reduce((n, g) => n + g.count, 0);

type GroupKey = (typeof GROUPS)[number]['key'];

@Component({
  selector: 'app-landing',
  imports: [RouterLink, Latex],
  template: `
    <div class="landing">
      <section class="hero">
        <div class="copy">
          <h1 class="reveal">Find the step where each derivation first goes wrong.</h1>
          <p class="lede reveal">
            Conxept checks every student step against their own previous step with SymPy, groups the
            first mistakes into named misconceptions across the class, and writes practice problems
            with verified answer keys.
          </p>
          <div class="ctas reveal">
            <a class="btn primary" routerLink="/">Open classes</a>
            <a class="btn" routerLink="/try">Try a derivation</a>
          </div>
        </div>
        <div class="orb-wrap" aria-hidden="true">
          <div class="orb">
            <div class="orb-glow"></div>
            <div class="orb-shine"></div>
            <div class="orb-label">
              <span class="spinner"></span>
              Checking derivations…
            </div>
          </div>
        </div>
      </section>

      <section class="block">
        <div class="block-head">
          <h2 class="reveal">Checked by mathematics, not a language model</h2>
          <p class="reveal">
            A step is valid when it equals the correct move applied to the student's own previous
            step. Later steps aren't blamed for an earlier mistake. Example from linear systems: an
            inverse Laplace transform by partial fractions.
          </p>
        </div>
        <ol class="derivation">
          <li class="line">
            <span class="tag">Given</span>
            <span [latex]="given"></span>
          </li>
          <li class="line">
            <span class="tag">Step 1</span>
            <span [latex]="step1"></span>
            <span class="verdict ok">Valid</span>
          </li>
          <li class="line wrong">
            <span class="tag">Step 2</span>
            <span [latex]="step2"></span>
            <span class="verdict bad">First wrong step</span>
          </li>
          <li class="line expected">
            <span class="tag">Expected</span>
            <span [latex]="expected"></span>
            <span class="verdict name">Dropped u(t) (causality)</span>
          </li>
        </ol>
      </section>

      <section class="block">
        <div class="block-head">
          <h2 class="reveal">A whole class at once</h2>
          <p class="reveal">
            Each cell is one derivation from a seeded demo class working linear-systems problems.
            Hover a group to find it.
          </p>
        </div>
        <div class="meter">
          <p class="count">
            <strong>{{ shown() }}</strong> <span>of {{ total }} derivations checked</span>
          </p>
          <div class="grid" role="img" [attr.aria-label]="summary">
            @for (c of cells; track $index) {
              <span class="cell {{ c }}" [class.dim]="focus() !== null && focus() !== c"></span>
            }
          </div>
          <ul class="legend">
            @for (g of groups; track g.key) {
              <li
                tabindex="0"
                (mouseenter)="focus.set(g.key)"
                (mouseleave)="focus.set(null)"
                (focus)="focus.set(g.key)"
                (blur)="focus.set(null)"
              >
                <span class="swatch {{ g.key }}"></span>
                <span class="lbl">{{ g.label }}</span>
                <span class="num">{{ g.count }}</span>
              </li>
            }
          </ul>
          <p class="fine">
            Synthetic class: 60 students, 8 problems, seed 7. This tests internal consistency, not
            accuracy on real students.
          </p>
        </div>
      </section>

      <section class="block facts">
        <div class="fact reveal">
          <h3>Verified practice</h3>
          <p>Every answer key is checked by two independent routes before it's shown.</p>
        </div>
        <div class="fact reveal">
          <h3>Same verdict every run</h3>
          <p>Sampling is seeded, so a diagnosis never changes between runs.</p>
        </div>
        <div class="fact reveal">
          <h3>No model in the checking path</h3>
          <p>Diagnosis runs offline. Errors outside the catalog are shown as Other, never named.</p>
        </div>
      </section>

      <section class="block closing reveal">
        <h2>See where your class is stuck.</h2>
        <a class="btn primary" routerLink="/">Open classes</a>
      </section>
    </div>
  `,
  styles: `
    :host {
      display: block;
      --l-bg: #07080c;
      --l-surface: #10121a;
      --l-line: #232634;
      --l-text: #eef0f6;
      --l-muted: #9aa0b4;
      --l-accent: #9bb0ff;
      --c-valid: #34d399;
      --c-named: #7c8cff;
      --c-other: #fb923c;
      --c-bad: #f87171;
    }
    .landing {
      background: var(--l-bg);
      color: var(--l-text);
      overflow: hidden;
    }
    section {
      max-width: 1120px;
      margin: 0 auto;
      padding: 0 24px;
    }
    .hero {
      min-height: calc(100vh - 56px);
      display: grid;
      grid-template-columns: 1.05fr 1fr;
      align-items: center;
      gap: 48px;
      padding-top: 48px;
      padding-bottom: 48px;
    }
    h1 {
      font-size: clamp(2.1rem, 4.6vw, 3.4rem);
      line-height: 1.05;
      letter-spacing: -0.03em;
      margin: 0 0 20px;
    }
    .lede {
      color: var(--l-muted);
      font-size: 1.08rem;
      max-width: 34em;
      margin: 0 0 28px;
    }
    .ctas {
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
    }
    .btn {
      display: inline-block;
      padding: 11px 20px;
      border-radius: 999px;
      border: 1px solid var(--l-line);
      color: var(--l-text);
      font-weight: 600;
      background: #ffffff0a;
    }
    .btn:hover {
      text-decoration: none;
      background: #ffffff14;
    }
    .btn.primary {
      background: var(--l-text);
      color: var(--l-bg);
      border-color: var(--l-text);
    }
    .btn.primary:hover {
      background: #ffffff;
    }

    .orb-wrap {
      display: grid;
      place-items: center;
    }
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

    .block {
      padding-top: 96px;
      padding-bottom: 96px;
    }
    .block-head {
      max-width: 40em;
      margin-bottom: 36px;
    }
    h2 {
      font-size: clamp(1.5rem, 3vw, 2.1rem);
      letter-spacing: -0.02em;
      line-height: 1.15;
      margin: 0 0 12px;
    }
    .block-head p {
      color: var(--l-muted);
      margin: 0;
      font-size: 1.02rem;
    }

    .derivation {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 12px;
      max-width: 760px;
    }
    .line {
      display: grid;
      grid-template-columns: 84px 1fr auto;
      align-items: center;
      gap: 16px;
      padding: 16px 20px;
      border-radius: 16px;
      background: var(--l-surface);
      border: 1px solid var(--l-line);
      overflow-x: auto;
    }
    .tag {
      color: var(--l-muted);
      font-size: 0.8rem;
      font-weight: 600;
    }
    .line.wrong {
      border-color: var(--c-bad);
      box-shadow: 0 0 0 4px #f8717118;
    }
    .line.expected {
      border-style: dashed;
    }
    .verdict {
      font-size: 0.78rem;
      font-weight: 650;
      padding: 4px 10px;
      border-radius: 999px;
      white-space: nowrap;
      justify-self: start;
    }
    .verdict.ok {
      color: var(--c-valid);
      background: #34d3991a;
    }
    .verdict.bad {
      color: var(--c-bad);
      background: #f871711f;
    }
    .verdict.name {
      color: var(--l-accent);
      background: #9bb0ff1a;
    }

    .meter {
      background: var(--l-surface);
      border: 1px solid var(--l-line);
      border-radius: 20px;
      padding: 24px;
    }
    .count {
      margin: 0 0 18px;
      color: var(--l-muted);
    }
    .count strong {
      color: var(--l-text);
      font-size: 1.9rem;
      font-variant-numeric: tabular-nums;
      letter-spacing: -0.02em;
      margin-right: 4px;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(60, 1fr);
      grid-template-rows: repeat(8, auto);
      grid-auto-flow: column;
      gap: 2px;
      padding: 10px;
      border-radius: 12px;
      background: #05060a;
      border: 1px solid var(--l-line);
    }
    .cell {
      aspect-ratio: 1;
      border-radius: 2px;
      transition: opacity 0.2s;
    }
    .cell.valid,
    .swatch.valid {
      background: var(--c-valid);
    }
    .cell.named,
    .swatch.named {
      background: var(--c-named);
    }
    .cell.other,
    .swatch.other {
      background: var(--c-other);
    }
    .cell.dim {
      opacity: 0.12 !important;
    }
    .legend {
      list-style: none;
      margin: 18px 0 0;
      padding: 0;
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }
    .legend li {
      display: flex;
      align-items: center;
      gap: 10px;
      padding: 8px 10px;
      border-radius: 10px;
      outline: none;
    }
    .legend li:hover,
    .legend li:focus-visible {
      background: #ffffff12;
    }
    .legend li:focus-visible {
      box-shadow: 0 0 0 2px var(--l-accent);
    }
    .swatch {
      width: 12px;
      height: 12px;
      border-radius: 3px;
    }
    .lbl {
      flex: 1;
      font-size: 0.9rem;
    }
    .num {
      color: var(--l-muted);
      font-variant-numeric: tabular-nums;
      font-size: 0.9rem;
    }
    .fine {
      color: var(--l-muted);
      font-size: 0.8rem;
      margin: 16px 0 0;
    }

    .facts {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 32px;
    }
    .fact h3 {
      font-size: 1rem;
      margin: 0 0 8px;
    }
    .fact p {
      color: var(--l-muted);
      margin: 0;
    }
    .closing {
      text-align: center;
      padding-bottom: 128px;
    }
    .closing h2 {
      margin-bottom: 24px;
    }

    @media (max-width: 820px) {
      .hero {
        grid-template-columns: 1fr;
        min-height: 0;
        gap: 32px;
      }
      .orb {
        width: min(320px, 76vw);
      }
      .facts,
      .legend {
        grid-template-columns: 1fr;
      }
      .grid {
        grid-template-columns: repeat(30, 1fr);
        grid-template-rows: repeat(16, auto);
      }
      .line {
        grid-template-columns: 1fr;
        gap: 8px;
      }
      .block {
        padding-top: 64px;
        padding-bottom: 64px;
      }
    }
  `,
})
export class LandingPage {
  readonly groups = GROUPS;
  readonly total = TOTAL;
  readonly cells: GroupKey[] = GROUPS.flatMap((g) => Array<GroupKey>(g.count).fill(g.key));
  readonly summary = GROUPS.map((g) => `${g.count} ${g.label.toLowerCase()}`).join(', ');
  readonly focus = signal<GroupKey | null>(null);
  readonly shown = signal(TOTAL);

  // f1-p1-q2-n0 with u(t) dropped at step 2: the engine's forgot_causality_u_of_t case.
  readonly given = String.raw`F(s) = \dfrac{s}{(s+1)(s+2)}`;
  readonly step1 = String.raw`\dfrac{2}{s+2} - \dfrac{1}{s+1}`;
  readonly step2 = String.raw`2e^{-2t} - e^{-t}`;
  readonly expected = String.raw`\left(2e^{-2t} - e^{-t}\right)u(t)`;

  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private scope?: Scope;
  private stopReveals = () => {};

  constructor() {
    afterNextRender(() => this.animate());
    inject(DestroyRef).onDestroy(() => {
      this.stopReveals();
      this.scope?.revert();
    });
  }

  private animate() {
    if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;

    // One-shot reveals play once their trigger's top passes 85% of the viewport. A scroll that
    // jumps clean over a section still plays it, so nothing can be left hidden.
    const pending = new Map<Element, JSAnimation[]>();
    const check = () => {
      for (const [el, anims] of pending) {
        if (el.getBoundingClientRect().top > innerHeight * 0.85) continue;
        anims.forEach((a) => a.play());
        pending.delete(el);
      }
      if (!pending.size) this.stopReveals();
    };
    addEventListener('scroll', check, { passive: true });
    addEventListener('resize', check, { passive: true });
    this.stopReveals = () => {
      removeEventListener('scroll', check);
      removeEventListener('resize', check);
    };
    const when = (selector: string | Element, ...anims: JSAnimation[]) => {
      const el = typeof selector === 'string' ? utils.$(selector)[0] : selector;
      if (el) pending.set(el, [...(pending.get(el) ?? []), ...anims]);
    };

    this.scope = createScope({ root: this.host.nativeElement }).add(() => {
      // Hero: copy rises in, the orb settles and its glow keeps turning slowly.
      animate('.hero .reveal', {
        opacity: [0, 1],
        y: [24, 0],
        delay: stagger(90),
        duration: 900,
        ease: 'out(3)',
      });
      animate('.orb', { opacity: [0, 1], scale: [0.86, 1], duration: 1400, ease: 'out(4)' });
      animate('.orb-glow', { rotate: 360, duration: 18000, ease: 'linear', loop: true });
      animate('.spinner', { rotate: 360, duration: 1600, ease: 'linear', loop: true });
      // The orb drifts up as the hero scrolls away.
      animate('.orb-wrap', {
        y: [0, -80],
        scale: [1, 0.9],
        ease: 'linear',
        autoplay: onScroll({ target: '.hero', enter: 'top top', leave: 'top bottom', sync: 0.4 }),
      });

      // Section headings and fact cards reveal once as they enter.
      utils.$('.block .reveal, .closing').forEach((el) => {
        when(
          el,
          animate(el, {
            opacity: [0, 1],
            y: [28, 0],
            duration: 800,
            ease: 'out(3)',
            autoplay: false,
          }),
        );
      });

      // Derivation: lines check in one by one, then the verdicts pop.
      const lines = animate('.derivation .line', {
        opacity: [0, 1],
        x: [-24, 0],
        delay: stagger(260),
        duration: 700,
        ease: 'out(3)',
        autoplay: false,
      });
      const verdicts = animate('.derivation .verdict', {
        opacity: [0, 1],
        scale: [0.6, 1],
        delay: stagger(260, { start: 420 }),
        duration: 500,
        ease: 'outBack(2)',
        autoplay: false,
      });

      // Meter: cells fill column by column while the counter climbs to the class total.
      const counter = { n: 0 };
      this.shown.set(0);
      const cells = animate('.grid .cell', {
        opacity: [0, 1],
        scale: [0.3, 1],
        delay: stagger(2.4),
        duration: 420,
        ease: 'out(2)',
        autoplay: false,
      });
      const count = animate(counter, {
        n: TOTAL,
        duration: TOTAL * 2.4 + 420,
        ease: 'linear',
        modifier: Math.round,
        onUpdate: () => this.shown.set(counter.n),
        autoplay: false,
      });
      when('.derivation', lines, verdicts);
      when('.meter', cells, count);
      check();
    });
  }
}
