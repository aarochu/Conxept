import { Routes } from '@angular/router';

import { ClassDashboard } from './pages/class-dashboard';
import { ClassList } from './pages/class-list';
import { ClusterPage } from './pages/cluster';
import { EvaluationPage } from './pages/evaluation';
import { LandingPage } from './pages/landing';
import { SubmissionPage } from './pages/submission';
import { TryPage } from './pages/try';

export const routes: Routes = [
  { path: '', component: ClassList, title: 'Classes · Conxept' },
  { path: 'welcome', component: LandingPage, title: 'Conxept' },
  { path: 'try', component: TryPage, title: 'Try a derivation · Conxept' },
  { path: 'class/:id', component: ClassDashboard, title: 'Dashboard · Conxept' },
  { path: 'class/:id/evaluation', component: EvaluationPage, title: 'Evaluation · Conxept' },
  { path: 'class/:id/cluster/:key', component: ClusterPage, title: 'Misconception · Conxept' },
  { path: 'class/:id/submission/:sid', component: SubmissionPage, title: 'Submission · Conxept' },
  { path: '**', redirectTo: '' },
];
