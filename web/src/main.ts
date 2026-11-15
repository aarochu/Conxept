import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { App } from './app/app';
import { loadSnapshot } from './app/snapshot';

loadSnapshot()
  .then(() => bootstrapApplication(App, appConfig))
  .catch((err) => console.error(err));
