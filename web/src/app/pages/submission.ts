import { Component, OnInit, inject, input, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import { Diagnosis, Problem, Submission } from '../../gen/misconception/v1/common_pb';
import { Api, errorMessage } from '../api';
import { DerivationView } from './derivation';

@Component({
  selector: 'app-submission',
  imports: [RouterLink, DerivationView],
  template: `
    <div class="page narrow">
      <div class="page-head">
        <div>
          <div class="crumbs">
            <a routerLink="/">Classes</a> / <a [routerLink]="['/class', id()]">Dashboard</a> /
          </div>
          <h1>{{ submission()?.studentLabel ?? 'Submission' }}</h1>
          <p class="sub">
            {{ problem()?.title }} <span class="mono">{{ submission()?.problemId }}</span>
          </p>
        </div>
      </div>
      @if (error()) {
        <div class="error" role="alert">{{ error() }}</div>
      }
      @if (submission()) {
        <section class="card">
          <app-derivation
            [problem]="problem()"
            [exprs]="exprs()"
            [diagnosis]="diagnosis()"
            [names]="names()"
          />
          @if (!diagnosis()) {
            <p class="note">This submission has not been processed yet.</p>
          }
        </section>
      }
    </div>
  `,
  styles: `
    .narrow {
      max-width: 860px;
    }
  `,
})
export class SubmissionPage implements OnInit {
  readonly id = input.required<string>();
  readonly sid = input.required<string>();
  private readonly api = inject(Api);

  readonly error = signal('');
  readonly submission = signal<Submission | undefined>(undefined);
  readonly diagnosis = signal<Diagnosis | undefined>(undefined);
  readonly problem = signal<Problem | undefined>(undefined);
  readonly exprs = signal<string[]>([]);
  readonly names = signal<Record<string, string>>({});

  async ngOnInit() {
    try {
      const [res, catalog] = await Promise.all([
        this.api.client.getSubmission({ submissionId: this.sid() }),
        this.api.catalog(),
      ]);
      this.submission.set(res.submission);
      this.diagnosis.set(res.diagnosis);
      this.exprs.set(
        [...(res.submission?.steps ?? [])].sort((a, b) => a.index - b.index).map((s) => s.expr),
      );
      this.names.set(Object.fromEntries([...catalog].map(([k, m]) => [k, m.name])));
      if (res.submission) this.problem.set(await this.api.problem(res.submission.problemId));
    } catch (e) {
      this.error.set(errorMessage(e));
    }
  }
}
