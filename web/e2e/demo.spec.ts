import { expect, test } from '@playwright/test';

test('record the three-minute synthetic demo without live Analyze', async ({ page }) => {
  const started = Date.now();
  // These waits pace a recording for a viewer; regression tests use assertions and controlled time.
  const at = async (second: number) => {
    const remaining = started + second * 1000 - Date.now();
    if (remaining > 0) await new Promise((resolve) => setTimeout(resolve, remaining));
  };
  const caption = async (text: string) => {
    await page.evaluate((message) => {
      let box = document.getElementById('demo-caption');
      if (!box) {
        box = document.createElement('aside');
        box.id = 'demo-caption';
        box.style.cssText =
          'position:fixed;bottom:0;left:0;right:0;padding:18px 32px;background:#101010f5;' +
          'color:#fff;font:20px/1.5 system-ui;z-index:9999;pointer-events:none;border-top:2px solid #9ba4ff';
        document.body.appendChild(box);
      }
      box.textContent = message;
    }, text);
  };

  await page.goto('/');
  await page.getByRole('button', { name: 'Seed synthetic class (60 students)' }).click();
  const row = page.locator('tbody tr').first();
  await expect(row.getByRole('button', { name: 'Process', exact: true })).toBeVisible();
  await caption(
    'Conxept: 60 students × 8 problems = 480 derivations. This walkthrough uses synthetic data.',
  );

  await at(20);
  await row.getByRole('button', { name: 'Process', exact: true }).click();
  await expect(row.getByRole('link', { name: 'Dashboard', exact: true })).toBeVisible();
  await caption(
    'Each step is checked against the student’s previous expression by mathematics. The model does not decide correctness.',
  );
  await row.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await expect(page.locator('.heat .cell:not(.none)')).toHaveCount(18);

  await at(50);
  await caption(
    'The heatmap shows where each derivation first went wrong. Each cell displays a count out of those who reached the step.',
  );
  await at(75);
  await page.getByRole('link', { name: /^Other 26 / }).click();
  await expect(page.getByRole('heading', { name: 'Not in the catalog' })).toBeVisible();
  await caption(
    'Errors outside the catalog are shown as Other. The tool does not invent a misconception name.',
  );
  await at(90);
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await page.getByRole('link', { name: /^Time-shift exponential sign flipped 23 / }).click();
  await caption(
    'Catalog errors have a named misconception, an explanation, and a targeted fix hint.',
  );

  await at(105);
  await page.locator('.examples a').first().click();
  await expect(page.getByText('First wrong step', { exact: true })).toBeVisible();
  await expect(page.getByText('Expected from their previous step', { exact: true })).toBeVisible();
  await caption(
    'The first wrong step is highlighted beside the expected expression. Later steps are not blamed for the earlier mistake.',
  );

  await at(125);
  await page.goBack();
  await page.getByRole('button', { name: 'Generate practice (3)' }).click();
  await expect(page.getByText('Verified', { exact: true })).toHaveCount(3);
  await caption(
    'Three practice problems target this misconception. Each answer key passed two verification routes.',
  );
  await at(135);
  await page.getByText('Verified', { exact: true }).nth(2).scrollIntoViewIfNeeded();

  await at(145);
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await page.getByRole('link', { name: 'Evaluation', exact: true }).click();
  await expect(page.getByText('313 of 313 flagged at the true first wrong step')).toBeVisible();
  await expect(page.getByText('235 of 235 catalog errors named correctly')).toBeVisible();
  await expect(page.getByText('78 of 78 errors outside the catalog caught')).toBeVisible();
  await caption(
    'These results test consistency on synthetic mistakes made by our own generator. They do not measure accuracy on real students.',
  );

  await at(165);
  await page.getByRole('link', { name: 'Dashboard', exact: true }).click();
  await page.getByRole('button', { name: 'Analyze class', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('ANTHROPIC_API_KEY');
  await caption(
    'Live Analyze is unavailable in this recording: no model key is configured. The diagnosis and verified-practice workflow runs without it.',
  );
  await at(180);
});
