import { Component, computed, input } from '@angular/core';

import { Diagnosis, DiagnosisStatus, Problem } from '../../gen/misconception/v1/common_pb';
import { Latex } from '../latex';

interface StepView {
  index: number;
  prompt: string;
  expr: string;
  state: 'valid' | 'diverged' | 'parse' | 'unchecked' | 'pending';
}

/** A derivation with the first wrong step highlighted and the expected value next to it. */
@Component({
  selector: 'app-derivation',
  imports: [Latex],
  template: `
    @if (problem(); as p) {
      <div class="given">
        <span class="muted label">Given</span>
        <div class="math" [latex]="p.givenLatex" [display]="true"></div>
      </div>
    }
    <ol class="steps">
      @for (s of views(); track s.index) {
        <li [class]="s.state">
          <div class="shead">
            <span class="sidx">Step {{ s.index }}</span>
            <span class="prompt">{{ s.prompt }}</span>
            <span class="state">
              @switch (s.state) {
                @case ('valid') { <span class="badge ok">Valid</span> }
                @case ('diverged') { <span class="badge bad">First wrong step</span> }
                @case ('parse') { <span class="badge bad">Cannot read</span> }
                @case ('unchecked') { <span class="badge">Not checked</span> }
              }
            </span>
          </div>
          @if (s.expr) {
            <div class="mono expr">{{ s.expr }}</div>
          }
          @if (s.state === 'diverged' && divergence(); as d) {
            <div class="compare">
              <div>
                <div class="muted label">Student wrote</div>
                <div class="math" [latex]="d.studentLatex"></div>
              </div>
              <div>
                <div class="muted label">Expected from their previous step</div>
                <div class="math" [latex]="d.expectedLatex"></div>
              </div>
            </div>
            <div class="labels">
              @for (m of d.misconceptionIds; track m) {
                <span class="badge accent">{{ names()[m] ?? m }}</span>
              }
              @if (d.misconceptionIds.length === 0) {
                <span class="badge">{{ d.residualLabel === 'unclassified' ? 'Other (not in catalog)' : d.residualLabel }}</span>
              }
            </div>
          }
          @if (s.state === 'parse') {
            <div class="perr">{{ diagnosis()?.parseError }}</div>
          }
        </li>
      }
    </ol>
    @if (hasUnchecked()) {
      <p class="muted foot">Later steps are not blamed for an earlier mistake; only the first divergence is reported.</p>
    }
  `,
  styles: `
    .given {
      margin-bottom: 12px;
    }
    .label {
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .math {
      overflow-x: auto;
      overflow-y: hidden;
    }
    .steps {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 10px;
    }
    .steps li {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 10px 14px;
    }
    .steps li.diverged,
    .steps li.parse {
      border-color: var(--bad);
      background: var(--bad-soft);
    }
    .steps li.unchecked {
      opacity: 0.6;
    }
    .shead {
      display: flex;
      gap: 10px;
      align-items: baseline;
    }
    .sidx {
      font-weight: 650;
      width: 52px;
      flex: none;
    }
    .prompt {
      color: var(--muted);
      font-size: 0.88rem;
      flex: 1;
    }
    .expr {
      margin: 6px 0 0 62px;
      word-break: break-all;
    }
    .compare {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 12px;
      margin: 10px 0 0 62px;
      background: var(--surface);
      border-radius: 8px;
      padding: 10px 12px;
    }
    @media (max-width: 700px) {
      .compare {
        grid-template-columns: 1fr;
        margin-left: 0;
      }
    }
    .labels {
      margin: 8px 0 0 62px;
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
    }
    .perr {
      margin: 6px 0 0 62px;
      color: var(--bad);
      font-size: 0.88rem;
    }
    .foot {
      font-size: 0.85rem;
      margin: 10px 0 0;
    }
  `,
})
export class DerivationView {
  readonly problem = input<Problem | undefined>();
  readonly exprs = input<string[]>([]);
  readonly diagnosis = input<Diagnosis | undefined>();
  readonly names = input<Record<string, string>>({});

  readonly divergence = computed(() => this.diagnosis()?.divergence);

  readonly views = computed<StepView[]>(() => {
    const p = this.problem();
    const d = this.diagnosis();
    const exprs = this.exprs();
    const n = Math.max(p?.steps.length ?? 0, exprs.length);
    const out: StepView[] = [];
    for (let i = 1; i <= n; i++) {
      let state: StepView['state'] = 'pending';
      if (d?.status === DiagnosisStatus.VALID) state = i <= exprs.length ? 'valid' : 'pending';
      else if (d?.status === DiagnosisStatus.DIVERGED) {
        const at = d.divergence?.stepIndex ?? 0;
        state = i < at ? 'valid' : i === at ? 'diverged' : i <= exprs.length ? 'unchecked' : 'pending';
      } else if (d?.status === DiagnosisStatus.PARSE_ERROR) {
        const at = d.parseErrorStep;
        state = i === at ? 'parse' : i < at ? 'pending' : i <= exprs.length ? 'unchecked' : 'pending';
      }
      out.push({ index: i, prompt: p?.steps.find((s) => s.index === i)?.prompt ?? '', expr: exprs[i - 1] ?? '', state });
    }
    return out;
  });

  readonly hasUnchecked = computed(() => this.views().some((v) => v.state === 'unchecked'));
}
