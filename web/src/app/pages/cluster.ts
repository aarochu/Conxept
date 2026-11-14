import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Misconception, Submission, Diagnosis } from '../../gen/misconception/v1/common_pb';
import { RemediationProblem } from '../../gen/misconception/v1/engine_pb';
import { create } from '@bufbuild/protobuf';

import { Cluster as ClusterMsg, ClusterSchema } from '../../gen/misconception/v1/gateway_pb';
import { Api, FAMILY_NAMES, errorMessage } from '../api';
import { Latex } from '../latex';

const MAX_EXAMPLES = 8;

interface Example {
  submission: Submission;
  diagnosis?: Diagnosis;
}

@Component({
  selector: 'app-cluster',
  imports: [RouterLink, Latex],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <div class="crumbs">
            <a routerLink="/">Classes</a> / <a [routerLink]="['/class', id()]">Dashboard</a> /
          </div>
          <h1>{{ cluster()?.name ?? key() }}</h1>
          @if (cluster(); as c) {
            <p class="sub">
              {{ c.count }} {{ c.count === 1 ? 'submission' : 'submissions' }} first went wrong here · {{ placesText() }}
            </p>
          }
        </div>
        @if (misconception()) {
          <button class="primary" (click)="practice()" [disabled]="generating()">
            {{ generating() ? 'Generating…' : 'Generate practice (3)' }}
          </button>
        }
      </div>

      @if (error()) {
        <div class="error" role="alert">{{ error() }}</div>
      }

      <div class="grid-2">
        <div class="stack">
          @if (misconception(); as m) {
            <section class="card">
              <h2>What happened</h2>
              <p>{{ m.description }}</p>
              <h3>Fix hint</h3>
              <p class="hint">{{ m.fixHint }}</p>
            </section>
          } @else if (cluster()) {
            <section class="card">
              <h2>Not in the catalog</h2>
              @if (key().startsWith('unclassified')) {
                <p>
                  These errors match no catalog misconception and no simple residual pattern. They are shown as
                  <strong>Other</strong>; the tool does not guess their cause. Read the examples to decide.
                </p>
              } @else {
                <p>
                  The step equals the correct answer transformed in a simple way (<span class="mono">{{ key() }}</span>),
                  but no catalog misconception explains it.
                </p>
              }
            </section>
          }

          @if (problems().length > 0) {
            <section class="card">
              <h2>Practice problems</h2>
              <p class="muted legend">
                Each answer key was checked by two independent routes. Each problem separates this misconception from
                the correct answer.
              </p>
              <div class="stack">
                @for (p of problems(); track p.problem?.id) {
                  <div class="practice">
                    <div class="ptitle">
                      <strong>{{ p.problem?.title }}</strong>
                      <span class="mono muted">{{ p.problem?.id }}</span>
                    </div>
                    <div class="math" [latex]="p.problem?.givenLatex ?? ''" [display]="true"></div>
                    <div class="kv">
                      <span class="muted">Answer key</span>
                      <span [latex]="p.answerKeyLatex"></span>
                    </div>
                    <div class="kv">
                      <span class="muted">This misconception gives</span>
                      <span [latex]="p.whyItDiscriminates"></span>
                    </div>
                    <div class="routes">
                      @if (p.verified) {
                        <span class="badge ok">Verified</span>
                      }
                      @for (r of p.verificationRoutes; track r) {
                        <span class="badge">{{ r }}</span>
                      }
                    </div>
                  </div>
                }
              </div>
            </section>
          }
        </div>

        <section class="card">
          <h2>Examples</h2>
          @if (examples().length === 0) {
            <div class="empty">{{ loading() ? 'Loading…' : 'No examples.' }}</div>
          }
          <ul class="examples">
            @for (ex of examples(); track ex.submission.id) {
              <li>
                <a [routerLink]="['/class', id(), 'submission', ex.submission.id]">
                  <div class="crow">
                    <strong>{{ ex.submission.studentLabel }}</strong>
                    <span class="mono muted">{{ ex.submission.problemId }}</span>
                  </div>
                  @if (ex.diagnosis?.divergence; as d) {
                    <div class="math small" [latex]="d.studentLatex"></div>
                  }
                </a>
              </li>
            }
          </ul>
        </section>
      </div>
    </div>
  `,
  styles: `
    .legend {
      font-size: 0.85rem;
      margin: -6px 0 14px;
    }
    .hint {
      background: var(--accent-soft);
      border-radius: 8px;
      padding: 10px 12px;
      margin: 0;
    }
    .practice {
      border: 1px solid var(--border);
      border-radius: 8px;
      padding: 12px 14px;
    }
    .ptitle,
    .crow {
      display: flex;
      justify-content: space-between;
      gap: 12px;
      align-items: baseline;
    }
    .kv {
      display: flex;
      gap: 12px;
      align-items: baseline;
      font-size: 0.9rem;
      padding: 4px 0;
      flex-wrap: wrap;
    }
    .kv > .muted {
      width: 190px;
      flex: none;
    }
    .routes {
      display: flex;
      gap: 6px;
      margin-top: 8px;
    }
    .math {
      overflow-x: auto;
    }
    .math.small {
      font-size: 0.9rem;
      margin-top: 4px;
    }
    .examples {
      list-style: none;
      padding: 0;
      margin: 0;
      display: grid;
      gap: 4px;
    }
    .examples a {
      display: block;
      color: inherit;
      padding: 8px 10px;
      border-radius: 8px;
    }
    .examples a:hover {
      background: var(--surface-2);
      text-decoration: none;
    }
  `,
})
export class ClusterPage implements OnInit {
  readonly id = input.required<string>();
  readonly key = input.required<string>();
  private readonly api = inject(Api);

  readonly loading = signal(true);
  readonly error = signal('');
  readonly cluster = signal<ClusterMsg | undefined>(undefined);
  readonly places = signal<ClusterMsg[]>([]);
  readonly placesText = computed(() =>
    this.places()
      .map((p) => `${this.familyName(p.family)}, step ${p.stepIndex} (${p.count})`)
      .join('; '),
  );
  readonly misconception = signal<Misconception | undefined>(undefined);
  readonly examples = signal<Example[]>([]);
  readonly problems = signal<RemediationProblem[]>([]);
  readonly generating = signal(false);

  async ngOnInit() {
    try {
      const [clusters, catalog] = await Promise.all([
        this.api.client.getClusters({ classId: this.id() }),
        this.api.catalog(),
      ]);
      // A misconception can appear at several (family, step) places; merge them into one view.
      const rows = clusters.clusters.filter((x) => x.key === this.key());
      if (rows.length === 0) {
        this.error.set('This cluster is not in the class.');
        return;
      }
      this.places.set(rows);
      const c = create(ClusterSchema, {
        ...rows[0],
        count: rows.reduce((n, r) => n + r.count, 0),
        exampleSubmissionIds: rows.flatMap((r) => r.exampleSubmissionIds).slice(0, MAX_EXAMPLES),
      });
      this.cluster.set(c);
      this.misconception.set(c.inCatalog ? catalog.get(c.key) : undefined);
      const subs = await Promise.all(
        c.exampleSubmissionIds.map((sid) => this.api.client.getSubmission({ submissionId: sid })),
      );
      this.examples.set(
        subs.filter((s) => s.submission).map((s) => ({ submission: s.submission!, diagnosis: s.diagnosis })),
      );
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.loading.set(false);
    }
  }

  familyName(f: number) {
    return FAMILY_NAMES[f] ?? 'Unknown';
  }

  async practice() {
    this.generating.set(true);
    this.error.set('');
    try {
      const res = await this.api.client.generateRemediation({ misconceptionId: this.key(), count: 3 });
      this.problems.set(res.problems.filter((p) => p.verified));
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.generating.set(false);
    }
  }
}
