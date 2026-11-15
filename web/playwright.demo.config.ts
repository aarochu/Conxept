import { defineConfig } from '@playwright/test';
import base from './playwright.config';

export default defineConfig({
  ...base,
  testMatch: 'demo.spec.ts',
  testIgnore: [],
  timeout: 240_000,
  outputDir: './demo-results',
  use: {
    ...base.use,
    video: { mode: 'on', size: { width: 1440, height: 900 } },
    screenshot: 'on',
  },
});
