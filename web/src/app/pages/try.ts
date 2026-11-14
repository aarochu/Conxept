import { Component, effect, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { Diagnosis, Problem } from '../../gen/misconception/v1/common_pb';
import { Api, errorMessage } from '../api';
import { Latex } from '../latex';
import { DerivationView } from './derivation';

const DEBOUNCE_MS = 350;

@Component({
  selector: 'app-try',
  imports: [FormsModule, Latex, DerivationView],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>Try a derivation</h1>
          <p class="sub">Type each step in the Step DSL and see the diagnosis as you go.</p>
        </div>
      </div>
      @if (error()) {
        <div class="error" role="alert">{{ error() }}</div>
      }
      <div class="grid-2">
        <section class="card">
          <label class="field">
            <span class="muted lbl">Problem</span>
            <select [ngModel]="problemId()" (ngModelChange)="pick($event)">
              @for (p of problems(); track p.id) {
                <option [value]="p.id">{{ p.id }} · {{ p.title }}</option>
              }
            </select>
          </label>
          @if (problem(); as p) {
            <div class="math" [latex]="p.givenLatex" [display]="true"></div>
            @for (st of p.steps; track st.index; let i = $index) {
              <label class="field">
                <span class="muted lbl">Step {{ st.index }}: {{ st.prompt }}</span>
                <input
                  class="mono"
                  [ngModel]="steps()[i]"
                  (ngModelChange)="setStep(i, $event)"
                  spellcheck="false"
                  autocomplete="off"
                  maxlength="400"
                />
              </label>
            }
            <details class="dsl">
              <summary>Step DSL</summary>
              <p>
                Variables <code>t tau w s</code>; <code>u(x)</code> or <code>step(x)</code> is the
                unit step; <code>j</code> is the imaginary unit;
                <code>exp sin cos sqrt pi e inf</code>; <code>int(f, var, lo, hi)</code> is a
                definite integral; <code>^</code> is power. Each step is the right-hand side only.
              </p>
            </details>
          }
        </section>
        <section class="card">
          <h2>Diagnosis</h2>
          @if (!diagnosis()) {
            <div class="empty">{{ checking() ? 'Checking…' : 'Start typing a step.' }}</div>
          } @else {
            <app-derivation
              [exprs]="filled()"
              [diagnosis]="diagnosis()"
              [problem]="undefined"
              [names]="names()"
            />
            @if (diagnosis()?.status === 1 && filled().length < (problem()?.steps?.length ?? 0)) {
              <p class="muted small">Every step so far is valid.</p>
            }
          }
        </section>
      </div>
    </div>
  `,
  styles: `
    .field {
      display: grid;
      gap: 4px;
      margin-bottom: 12px;
    }
    .lbl {
      font-size: 0.82rem;
    }
    .math {
      overflow-x: auto;
      margin: 4px 0 12px;
    }
    .dsl {
      font-size: 0.85rem;
      color: var(--muted);
    }
    .dsl code {
      font-family: var(--mono);
      color: var(--text);
    }
    .small {
      font-size: 0.85rem;
    }
  `,
})
export class TryPage {
  private readonly api = inject(Api);
  readonly problems = signal<Problem[]>([]);
  readonly problemId = signal('');
  readonly problem = signal<Problem | undefined>(undefined);
  readonly steps = signal<string[]>([]);
  readonly filled = signal<string[]>([]);
  readonly diagnosis = signal<Diagnosis | undefined>(undefined);
  readonly checking = signal(false);
  readonly error = signal('');
  readonly names = signal<Record<string, string>>({});
  private seq = 0;

  constructor() {
    this.init();
    effect((onCleanup) => {
      const pid = this.problemId();
      const leading: string[] = [];
      for (const s of this.steps()) {
        if (!s.trim()) break;
        leading.push(s.trim());
      }
      if (!pid || leading.length === 0) {
        this.seq++; // drop any response still in flight for the old input
        this.diagnosis.set(undefined);
        this.checking.set(false);
        return;
      }
      const timer = setTimeout(() => this.check(pid, leading), DEBOUNCE_MS);
      onCleanup(() => clearTimeout(timer));
    });
  }

  private async init() {
    try {
      const [problems, catalog] = await Promise.all([this.api.problems(), this.api.catalog()]);
      this.problems.set(problems);
      this.names.set(Object.fromEntries([...catalog].map(([k, m]) => [k, m.name])));
      if (problems.length) this.pick(problems[0].id);
    } catch (e) {
      this.error.set(errorMessage(e));
    }
  }

  pick(id: string) {
    const p = this.problems().find((x) => x.id === id);
    this.problemId.set(id);
    this.problem.set(p);
    this.steps.set(p ? p.steps.map(() => '') : []);
    this.seq++; // a response for the previous problem must not land on this one
    this.diagnosis.set(undefined);
    this.checking.set(false);
  }

  setStep(i: number, value: string) {
    this.steps.update((all) => all.map((s, j) => (j === i ? value : s)));
  }

  private async check(problemId: string, exprs: string[]) {
    const mine = ++this.seq;
    this.checking.set(true);
    try {
      const res = await this.api.client.tryDerivation({
        problemId,
        steps: exprs.map((expr, i) => ({ index: i + 1, expr })),
      });
      if (mine !== this.seq) return;
      this.filled.set(exprs);
      this.diagnosis.set(res.diagnosis);
      this.error.set('');
    } catch (e) {
      if (mine === this.seq) this.error.set(errorMessage(e));
    } finally {
      if (mine === this.seq) this.checking.set(false);
    }
  }
}
