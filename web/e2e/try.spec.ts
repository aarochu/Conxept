import { expect, test } from '@playwright/test';

test('an old verdict cannot land while edited input is waiting for debounce', async ({ page }) => {
  await page.clock.install({ time: new Date('2026-11-14T07:00:00Z') });
  await page.goto('/try');
  const firstStep = page.getByRole('textbox', { name: 'Step 1:', exact: false });
  await expect(firstStep).toBeVisible();
  await page.clock.pauseAt(new Date('2026-11-14T08:00:00Z'));

  let releaseOld!: () => void;
  let firstReceived!: () => void;
  const held = new Promise<void>((resolve) => (releaseOld = resolve));
  const received = new Promise<void>((resolve) => (firstReceived = resolve));
  let first = true;
  await page.route('**/TryDerivation', async (route) => {
    if (!first) return route.continue();
    first = false;
    const response = await route.fetch();
    firstReceived();
    await held;
    await route.fulfill({ response });
  });

  await firstStep.fill('2/(s+2) - 1/(s+1)');
  await page.clock.runFor(400);
  await received;
  await firstStep.fill('1');
  const delivered = page.waitForResponse('**/TryDerivation');
  releaseOld();
  await delivered;
  await page.clock.runFor(50);
  await expect(page.getByText('Every step so far is valid.', { exact: true })).not.toBeVisible();

  await page.clock.resume();
  await expect(page.getByText('First wrong step', { exact: true })).toBeVisible();
});
