import { Routes } from '@angular/router';

import { ClassDashboard } from './pages/class-dashboard';
import { ClassList } from './pages/class-list';
import { ClusterPage } from './pages/cluster';
import { EvaluationPage } from './pages/evaluation';
import { LandingPage } from './pages/landing';
import { SubmissionPage } from './pages/submission';
import { TryPage } from './pages/try';

export const routes: Routes = [
  { path: '', component: ClassList, title: 'Classes · ConXept' },
  { path: 'welcome', component: LandingPage, title: 'ConXept' },
  { path: 'try', component: TryPage, title: 'Try a derivation · ConXept' },
  { path: 'class/:id', component: ClassDashboard, title: 'Dashboard · ConXept' },
  { path: 'class/:id/evaluation', component: EvaluationPage, title: 'Evaluation · ConXept' },
  { path: 'class/:id/cluster/:key', component: ClusterPage, title: 'Misconception · ConXept' },
  { path: 'class/:id/submission/:sid', component: SubmissionPage, title: 'Submission · ConXept' },
  { path: '**', redirectTo: '' },
];
