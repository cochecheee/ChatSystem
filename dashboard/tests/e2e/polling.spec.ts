import { expect, test } from '@playwright/test';
import { injectFinding, resetTestDb } from './helpers';

test.beforeEach(async () => { await resetTestDb(); });

test('findings count updates in sidebar after inject', async ({ page }) => {
  await page.goto('/');

  // Inject a finding via test API
  await injectFinding('HIGH', 'test-sqli');

  // Navigate to Vulnerabilities to trigger a re-fetch
  await page.click('[data-nav="vulns"]');

  // Expect at least one finding row to appear
  await expect(page.locator('[data-testid="finding-row"]').first()).toBeVisible({ timeout: 15000 });
});

test('overview page loads without errors', async ({ page }) => {
  await page.goto('/');
  await expect(page.locator('text=Security overview')).toBeVisible({ timeout: 8000 });
  // No crash
  const errors: string[] = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.waitForTimeout(1000);
  expect(errors).toHaveLength(0);
});
