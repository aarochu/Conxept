import { Component, OnInit, computed, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';
import { marked } from 'marked';

import { Problem } from '../../gen/misconception/v1/common_pb';
import { Cluster, HeatmapCell } from '../../gen/misconception/v1/gateway_pb';
import { Api, FAMILY_NAMES, errorMessage } from '../api';

interface LogLine {
  kind: 'call' | 'result' | 'text' | 'error';
  title: string;
  detail: string;
}

interface HeatRow {
  problem: Problem;
  cells: (HeatmapCell | null)[];
}

@Component({
  selector: 'app-class-dashboard',
  imports: [RouterLink],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <div class="crumbs"><a routerLink="/">Classes</a> /</div>
          <h1>{{ className() || 'Class' }}</h1>
          <p class="sub">
            Where each submission first goes wrong, checked by mathematics against the student's own previous step.
          </p>
        </div>
        <div class="head-actions">
          <a class="btn" [routerLink]="['/class', id(), 'evaluation']">Evaluation</a>
          <button class="primary" (click)="analyze()" [disabled]="analyzing()">
            {{ analyzing() ? 'Analyzing…' : 'Analyze class' }}
          </button>
        </div>
      </div>

      @if (error()) {
        <div class="error" role="alert">{{ error() }}</div>
      }

      <div class="grid-2">
        <section class="card">
          <h2>First wrong step, by problem</h2>
          <p class="muted legend">
            Each cell is one step. The number is how many students first went wrong there, out of those who reached it.
          </p>
          @if (rows().length === 0) {
            <div class="empty">{{ loading() ? 'Loading…' : 'No diagnoses yet. Process the class first.' }}</div>
          } @else {
            <div class="scroll">
            <table class="heat">
              <thead>
                <tr>
                  <th>Problem</th>
                  @for (s of stepCols(); track s) {
                    <th class="center">Step {{ s }}</th>
                  }
                </tr>
              </thead>
              <tbody>
                @for (r of rows(); track r.problem.id) {
                  <tr>
                    <td>
                      <div class="pname">{{ familyName(r.problem.family) }}</div>
                      <div class="mono muted">{{ r.problem.id }}</div>
                    </td>
                    @for (c of r.cells; track $index) {
                      @if (c) {
                        <td class="cell" [style.background]="shade(c)" [class.hot]="ratio(c) > 0.45"
                            [attr.title]="c.failed + ' of ' + c.attempted + ' first went wrong here'">
                          <span class="n">{{ c.failed }}</span><span class="of">/ {{ c.attempted }}</span>
                        </td>
                      } @else {
                        <td class="cell none"></td>
                      }
                    }
                  </tr>
                }
              </tbody>
            </table>
            </div>
          }
        </section>

        <section class="card">
          <h2>Misconceptions</h2>
          @if (clusters().length === 0) {
            <div class="empty">{{ loading() ? 'Loading…' : 'No errors found.' }}</div>
          } @else {
            <ul class="clusters">
              <!-- One misconception can appear at several (family, step) places, so the key alone is not unique. -->
              @for (c of clusters(); track c.key + ':' + c.family + ':' + c.stepIndex) {
                <li>
                  <a [routerLink]="['/class', id(), 'cluster', c.key]">
                    <div class="crow">
                      <span class="cname">{{ c.name }}</span>
                      <span class="count">{{ c.count }}</span>
                    </div>
                    <div class="bar"><div [style.width.%]="(100 * c.count) / maxCount()"></div></div>
                    <div class="cmeta">
                      {{ familyName(c.family) }}, step {{ c.stepIndex }}
                      @if (c.inCatalog) {
                        <span class="badge accent">Catalog</span>
                      } @else if (c.key.startsWith('unclassified')) {
                        <span class="badge">Other</span>
                      } @else {
                        <span class="badge">Residual</span>
                      }
                    </div>
                  </a>
                </li>
              }
            </ul>
          }
        </section>
      </div>

      @if (log().length > 0 || brief()) {
        <section class="card analyze">
          <h2>Instructor brief</h2>
          <p class="muted legend">
            The agent writes the summary. Every number in it must come from a tool result, or the brief is rejected.
          </p>
          <ol class="log">
            @for (l of log(); track $index) {
              <li [class]="l.kind">
                <span class="tag">{{ l.kind === 'call' ? 'tool' : l.kind === 'result' ? 'result' : l.kind }}</span>
                <span class="mono">{{ l.title }}</span>
                <span class="muted detail">{{ l.detail }}</span>
              </li>
            }
          </ol>
          @if (brief()) {
            <article class="brief" [innerHTML]="brief()"></article>
          }
        </section>
      }
    </div>
  `,
  styles: `
    .head-actions {
      display: flex;
      gap: 8px;
    }
    .legend {
      font-size: 0.85rem;
      margin: -6px 0 14px;
    }
    .scroll {
      overflow-x: auto;
    }
    .heat th.center {
      text-align: center;
    }
    .heat td {
      border-bottom: 2px solid var(--surface);
    }
    .pname {
      font-weight: 550;
    }
    .cell {
      text-align: center;
      border-left: 2px solid var(--surface);
      border-radius: 6px;
      min-width: 76px;
      font-variant-numeric: tabular-nums;
    }
    .cell.none {
      background: transparent;
    }
    .cell .n {
      font-weight: 700;
      font-size: 1.05rem;
    }
    .cell .of {
      font-size: 0.75rem;
      margin-left: 3px;
      opacity: 0.75;
    }
    .cell.hot {
      color: #fff;
    }
    .clusters {
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 4px;
    }
    .clusters a {
      display: block;
      color: inherit;
      padding: 8px 10px;
      border-radius: 8px;
    }
    .clusters a:hover {
      background: var(--surface-2);
      text-decoration: none;
    }
    .crow {
      display: flex;
      justify-content: space-between;
      gap: 12px;
    }
    .cname {
      font-weight: 550;
    }
    .count {
      font-weight: 700;
      font-variant-numeric: tabular-nums;
    }
    .bar {
      height: 4px;
      background: var(--surface-2);
      border-radius: 99px;
      margin: 6px 0;
    }
    .bar > div {
      height: 100%;
      background: var(--heat);
      border-radius: 99px;
    }
    .cmeta {
      font-size: 0.8rem;
      color: var(--muted);
      display: flex;
      gap: 8px;
      align-items: center;
    }
    .analyze {
      margin-top: 16px;
    }
    .log {
      list-style: none;
      padding: 0;
      margin: 0 0 16px;
      display: grid;
      gap: 4px;
      font-size: 0.85rem;
    }
    .log li {
      display: flex;
      gap: 10px;
      align-items: baseline;
    }
    .log .tag {
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--muted);
      width: 52px;
      flex: none;
    }
    .log li.error .tag,
    .log li.error .detail {
      color: var(--bad);
    }
    .detail {
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .brief {
      border-top: 1px solid var(--border);
      padding-top: 12px;
    }
  `,
})
export class ClassDashboard implements OnInit {
  readonly id = input.required<string>();
  private readonly api = inject(Api);

  readonly className = signal('');
  readonly loading = signal(true);
  readonly error = signal('');
  readonly problems = signal<Problem[]>([]);
  readonly cells = signal<HeatmapCell[]>([]);
  readonly clusters = signal<Cluster[]>([]);
  readonly analyzing = signal(false);
  readonly log = signal<LogLine[]>([]);
  readonly brief = signal('');

  readonly stepCols = computed(() => {
    const max = Math.max(0, ...this.problems().map((p) => p.steps.length));
    return Array.from({ length: max }, (_, i) => i + 1);
  });

  readonly rows = computed<HeatRow[]>(() => {
    const byKey = new Map(this.cells().map((c) => [`${c.problemId}:${c.stepIndex}`, c]));
    const withData = new Set(this.cells().map((c) => c.problemId));
    return this.problems()
      .filter((p) => withData.has(p.id))
      .map((p) => ({
        problem: p,
        cells: this.stepCols().map((s) => byKey.get(`${p.id}:${s}`) ?? null),
      }));
  });

  readonly maxCount = computed(() => Math.max(1, ...this.clusters().map((c) => c.count)));

  async ngOnInit() {
    const classId = this.id();
    try {
      const [classes, problems, heat, clusters] = await Promise.all([
        this.api.client.listClasses({}),
        this.api.problems(),
        this.api.client.getHeatmap({ classId }),
        this.api.client.getClusters({ classId }),
      ]);
      this.className.set(classes.classes.find((c) => c.id === classId)?.name ?? '');
      this.problems.set(problems);
      this.cells.set(heat.cells);
      this.clusters.set(clusters.clusters);
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.loading.set(false);
    }
  }

  familyName(f: number) {
    return FAMILY_NAMES[f] ?? 'Unknown';
  }

  ratio(c: HeatmapCell) {
    return c.attempted ? c.failed / c.attempted : 0;
  }

  /** One sequential ramp; the number is always shown, never colour alone. */
  shade(c: HeatmapCell) {
    const pct = Math.round(8 + 80 * Math.min(1, this.ratio(c) / 0.6));
    return `color-mix(in oklab, var(--heat) ${c.failed === 0 ? 0 : pct}%, var(--surface-2))`;
  }

  async analyze() {
    this.analyzing.set(true);
    this.error.set('');
    this.log.set([]);
    this.brief.set('');
    const add = (l: LogLine) => this.log.update((all) => [...all, l]);
    try {
      for await (const m of this.api.client.analyzeClass({ classId: this.id() })) {
        const ev = m.event?.event;
        if (!ev) continue;
        switch (ev.case) {
          case 'toolCall':
            add({ kind: 'call', title: ev.value.name, detail: ev.value.argumentsText });
            break;
          case 'toolResult':
            add({ kind: 'result', title: ev.value.name, detail: ev.value.summary });
            break;
          case 'brief':
            this.brief.set(await marked.parse(ev.value.markdown));
            break;
          case 'error':
            add({ kind: 'error', title: 'error', detail: ev.value });
            break;
        }
      }
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.analyzing.set(false);
    }
  }
}
