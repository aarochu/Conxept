import { Component, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { ClassInfo } from '../../gen/misconception/v1/gateway_pb';
import { Api, errorMessage } from '../api';

interface Progress {
  done: number;
  total: number;
}

@Component({
  selector: 'app-class-list',
  imports: [RouterLink],
  template: `
    <div class="page">
      <div class="page-head">
        <div>
          <h1>Classes</h1>
          <p class="sub">Seed a synthetic class, process it, and see where the class is stuck.</p>
        </div>
        <button class="primary" (click)="seed()" [disabled]="seeding()">
          {{ seeding() ? 'Seeding…' : 'Seed synthetic class (60 students)' }}
        </button>
      </div>

      @if (error()) {
        <div class="error" role="alert">{{ error() }}</div>
      }

      <div class="card">
        @if (loading()) {
          <div class="empty">Loading…</div>
        } @else if (classes().length === 0) {
          <div class="empty">No classes yet. Seed one to start.</div>
        } @else {
          <table>
            <thead>
              <tr>
                <th>Class</th>
                <th class="num">Submissions</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              @for (c of classes(); track c.id) {
                <tr>
                  <td>
                    @if (c.processed) {
                      <a [routerLink]="['/class', c.id]">{{ c.name }}</a>
                    } @else {
                      {{ c.name }}
                    }
                  </td>
                  <td class="num">{{ c.numSubmissions }}</td>
                  <td>
                    @if (progress()[c.id]; as p) {
                      <div
                        class="progress"
                        [attr.aria-label]="'Processed ' + p.done + ' of ' + p.total"
                      >
                        <div [style.width.%]="p.total ? (100 * p.done) / p.total : 100"></div>
                      </div>
                      <span class="muted small">{{ p.done }} / {{ p.total }}</span>
                    } @else if (c.processed) {
                      <span class="badge ok">Processed</span>
                    } @else {
                      <span class="badge">Not processed</span>
                    }
                  </td>
                  <td class="actions">
                    <button (click)="process(c)" [disabled]="!!progress()[c.id]">
                      {{ c.processed ? 'Reprocess' : 'Process' }}
                    </button>
                    @if (c.processed) {
                      <a class="btn" [routerLink]="['/class', c.id]">Dashboard</a>
                      <a class="btn" [routerLink]="['/class', c.id, 'evaluation']">Evaluation</a>
                    }
                  </td>
                </tr>
              }
            </tbody>
          </table>
        }
      </div>
    </div>
  `,
  styles: `
    .actions {
      display: flex;
      gap: 8px;
      justify-content: flex-end;
    }
    td .progress {
      display: inline-block;
      width: 140px;
      vertical-align: middle;
      margin-right: 8px;
    }
    .small {
      font-size: 0.82rem;
      font-variant-numeric: tabular-nums;
    }
  `,
})
export class ClassList {
  private readonly api = inject(Api);
  readonly classes = signal<ClassInfo[]>([]);
  readonly loading = signal(true);
  readonly seeding = signal(false);
  readonly error = signal('');
  readonly progress = signal<Record<string, Progress>>({});

  constructor() {
    this.load();
  }

  async load() {
    try {
      this.classes.set((await this.api.client.listClasses({})).classes);
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.loading.set(false);
    }
  }

  async seed() {
    this.seeding.set(true);
    this.error.set('');
    try {
      await this.api.client.seedSyntheticClass({ numStudents: 60 });
      await this.load();
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.seeding.set(false);
    }
  }

  async process(c: ClassInfo) {
    this.error.set('');
    this.setProgress(c.id, { done: 0, total: c.numSubmissions });
    try {
      for await (const m of this.api.client.processClass({ classId: c.id })) {
        this.setProgress(c.id, { done: m.done, total: m.total });
      }
      await this.load();
    } catch (e) {
      this.error.set(errorMessage(e));
    } finally {
      this.setProgress(c.id, undefined);
    }
  }

  private setProgress(id: string, p: Progress | undefined) {
    this.progress.update((all) => {
      const next = { ...all };
      if (p) next[id] = p;
      else delete next[id];
      return next;
    });
  }
}
