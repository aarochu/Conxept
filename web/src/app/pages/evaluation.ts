import { Component, OnInit, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { GetEvaluationResponse } from '../../gen/misconception/v1/gateway_pb';
import { Api, errorMessage, pct } from '../api';

@Component({
  selector: 'app-evaluation',
  imports: [RouterLink],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <div class="crumbs">
            <a routerLink="/">Classes</a> / <a [routerLink]="['/class', id()]">Dashboard</a> /
          </div>
          <h1>Evaluation</h1>
          <p class="sub">
            The engine's diagnoses compared with the synthetic class's ground truth.
          </p>
        </div>
      </div>
      @if (error()) {
        <div class="error" role="alert">{{ error() }}</div>
      }
      @if (ev(); as e) {
        @if (e.total === 0) {
          <div class="card empty">
            This class has no ground truth (only synthetic classes do) or has not been processed.
          </div>
        } @else {
          <div class="tiles">
            <div class="card tile">
              <div class="muted lbl">False alarms</div>
              <div class="big">{{ e.falseAlarms }}</div>
              <div class="muted small">of {{ e.correctSubmissions }} correct submissions</div>
            </div>
            <div class="card tile">
              <div class="muted lbl">Step accuracy</div>
              <div class="big">{{ pct(e.divergenceStepCorrect, e.divergenceStepExpected) }}</div>
              <div class="muted small">
                {{ e.divergenceStepCorrect }} of {{ e.divergenceStepExpected }} flagged at the true
                first wrong step
              </div>
            </div>
            <div class="card tile">
              <div class="muted lbl">Label accuracy</div>
              <div class="big">{{ pct(e.labelCorrect, e.labelExpected) }}</div>
              <div class="muted small">
                {{ e.labelCorrect }} of {{ e.labelExpected }} catalog errors named correctly
              </div>
            </div>
            <div class="card tile">
              <div class="muted lbl">Held-out detection</div>
              <div class="big">{{ pct(e.heldoutDetected, e.heldoutExpected) }}</div>
              <div class="muted small">
                {{ e.heldoutDetected }} of {{ e.heldoutExpected }} errors outside the catalog caught
              </div>
            </div>
          </div>

          <p class="note">
            This is a synthetic class built from our own error catalog, so it tests consistency, not
            real students.
          </p>

          @if (e.perLabel.length > 0) {
            <section class="card">
              <h2>Per misconception</h2>
              <table>
                <thead>
                  <tr>
                    <th>Misconception</th>
                    <th class="num">True positive</th>
                    <th class="num">False positive</th>
                    <th class="num">False negative</th>
                  </tr>
                </thead>
                <tbody>
                  @for (l of e.perLabel; track l.label) {
                    <tr>
                      <td>{{ names()[l.label] ?? l.label }}</td>
                      <td class="num">{{ l.truePositive }}</td>
                      <td class="num">{{ l.falsePositive }}</td>
                      <td class="num">{{ l.falseNegative }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </section>
          }
        }
      }
    </div>
  `,
  styles: `
    .tiles {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 16px;
      margin-bottom: 16px;
    }
    .lbl {
      font-size: 0.8rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }
    .big {
      font-size: 2.1rem;
      font-weight: 700;
      letter-spacing: -0.02em;
      font-variant-numeric: tabular-nums;
      margin: 2px 0;
    }
    .small {
      font-size: 0.85rem;
    }
    .note {
      margin: 0 0 16px;
    }
  `,
})
export class EvaluationPage implements OnInit {
  readonly id = input.required<string>();
  private readonly api = inject(Api);
  readonly ev = signal<GetEvaluationResponse | undefined>(undefined);
  readonly error = signal('');
  readonly names = signal<Record<string, string>>({});
  readonly pct = pct;

  async ngOnInit() {
    try {
      const [ev, catalog] = await Promise.all([
        this.api.client.getEvaluation({ classId: this.id() }),
        this.api.catalog(),
      ]);
      this.ev.set(ev);
      this.names.set(Object.fromEntries([...catalog].map(([k, m]) => [k, m.name])));
    } catch (e) {
      this.error.set(errorMessage(e));
    }
  }
}
