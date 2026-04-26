import { expect, test } from '@playwright/test';
import { injectFinding, loginViaUI, resetTestDb } from './helpers';

test.beforeEach(async () => { await resetTestDb(); });

test('/report downloads security-report.html', async ({ page }) => {
  await injectFinding('HIGH');
  await injectFinding('CRITICAL');
  await loginViaUI(page, 'developer');

  const downloadPromise = page.waitForEvent('download');
  await page.fill('[data-testid="chat-input"]', '/report');
  await page.keyboard.press('Enter');

  const download = await downloadPromise;
  expect(download.suggestedFilename()).toBe('security-report.html');

  const path = await download.path();
  const { readFileSync } = await import('fs');
  const content = readFileSync(path!, 'utf-8');
  expect(content).toContain('Sentinel SAST');
  expect(content).toContain('findings');
});

test('/report shows success message in chat', async ({ page }) => {
  await loginViaUI(page, 'developer');

  page.waitForEvent('download').catch(() => {});
  await page.fill('[data-testid="chat-input"]', '/report');
  await page.keyboard.press('Enter');

  await expect(page.locator('.msg.ai').last()).toContainText(/báo cáo|tải xuống/i, { timeout: 15000 });
});
