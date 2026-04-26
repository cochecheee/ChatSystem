import { expect, test } from '@playwright/test';
import { getToken, injectFinding, loginViaUI, resetTestDb } from './helpers';

test.beforeEach(async () => { await resetTestDb(); });

test('developer login shows chat interface', async ({ page }) => {
  await loginViaUI(page, 'developer');
  await expect(page.locator('text=Sentinel AI')).toBeVisible();
  await expect(page.locator('[data-testid="chat-input"]')).toBeVisible();
});

test('/explain with valid finding returns AI analysis', async ({ page }) => {
  const findingId = await injectFinding('HIGH', 'java.sql-injection');
  await loginViaUI(page, 'developer');

  await page.fill('[data-testid="chat-input"]', `/explain ${findingId}`);
  await page.keyboard.press('Enter');

  await expect(page.locator('.msg.ai').last()).not.toContainText('⏳', { timeout: 20000 });
  await expect(page.locator('.msg.ai').last()).toContainText(/#\d+|Finding|phân tích/i);
});

test('/explain with unknown finding id shows error', async ({ page }) => {
  await loginViaUI(page, 'developer');
  await page.fill('[data-testid="chat-input"]', '/explain 99999');
  await page.keyboard.press('Enter');

  await expect(page.locator('.msg.ai').last()).toContainText(/lỗi|404|không tìm thấy/i, { timeout: 10000 });
});

test('/scan requires security_lead role — developer gets error', async ({ page }) => {
  await loginViaUI(page, 'developer');
  await page.fill('[data-testid="chat-input"]', '/scan');
  await page.keyboard.press('Enter');

  await expect(page.locator('.msg.ai').last()).toContainText(/403|quyền|role/i, { timeout: 10000 });
});

test('/status shows fallback message', async ({ page }) => {
  await loginViaUI(page, 'developer');
  await page.fill('[data-testid="chat-input"]', '/status');
  await page.keyboard.press('Enter');

  await expect(page.locator('.msg.ai').last()).toBeVisible({ timeout: 5000 });
});
