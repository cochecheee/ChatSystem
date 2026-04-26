import { expect, test } from '@playwright/test';
import { injectFinding, loginViaUI, resetTestDb } from './helpers';

test.beforeEach(async () => { await resetTestDb(); });

test('developer cannot /approve — gets 403 error', async ({ page }) => {
  const id = await injectFinding('HIGH');
  await loginViaUI(page, 'developer');

  await page.fill('[data-testid="chat-input"]', `/approve ${id}`);
  await page.keyboard.press('Enter');

  await expect(page.locator('.msg.ai').last()).toContainText(/403|quyền/i, { timeout: 10000 });
});

test('full approve flow — dialog opens, validates, submits', async ({ page }) => {
  const id = await injectFinding('HIGH');
  await loginViaUI(page, 'security_lead');

  await page.fill('[data-testid="chat-input"]', `/approve ${id}`);
  await page.keyboard.press('Enter');

  // Dialog should open
  await expect(page.locator('text=Phê duyệt Finding')).toBeVisible({ timeout: 5000 });
  await expect(page.locator(`text=Finding #${id}`)).toBeVisible();

  // Short justification — confirm disabled
  await page.fill('textarea', 'Too short');
  await expect(page.locator('button:has-text("Xác nhận phê duyệt")')).toBeDisabled();

  // Valid justification — confirm enabled
  await page.fill('textarea', 'False positive — input is validated upstream by SecurityFilter class');
  await expect(page.locator('button:has-text("Xác nhận phê duyệt")')).toBeEnabled();

  await page.click('button:has-text("Xác nhận phê duyệt")');

  // Dialog closes
  await expect(page.locator('text=Phê duyệt Finding')).not.toBeVisible({ timeout: 5000 });
  // AI message confirms
  await expect(page.locator('.msg.ai').last()).toContainText(/phê duyệt/i, { timeout: 10000 });
});

test('revoke after approve — dialog has destructive button', async ({ page }) => {
  const id = await injectFinding('HIGH');
  await loginViaUI(page, 'security_lead');

  // Approve first
  await page.fill('[data-testid="chat-input"]', `/approve ${id}`);
  await page.keyboard.press('Enter');
  await expect(page.locator('text=Phê duyệt Finding')).toBeVisible({ timeout: 5000 });
  await page.fill('textarea', 'False positive — input validated upstream by SecurityFilter');
  await page.click('button:has-text("Xác nhận phê duyệt")');
  await expect(page.locator('text=Phê duyệt Finding')).not.toBeVisible({ timeout: 5000 });

  // Now revoke
  await page.fill('[data-testid="chat-input"]', `/revoke ${id}`);
  await page.keyboard.press('Enter');
  await expect(page.locator('text=Thu hồi phê duyệt')).toBeVisible({ timeout: 5000 });

  // Confirm button should have danger styling
  const confirmBtn = page.locator('button:has-text("Thu hồi")').last();
  await expect(confirmBtn).toHaveClass(/danger/);

  await page.fill('textarea', 'New evidence shows this is actually exploitable via X endpoint');
  await confirmBtn.click();
  await expect(page.locator('text=Thu hồi phê duyệt')).not.toBeVisible({ timeout: 5000 });
  await expect(page.locator('.msg.ai').last()).toContainText(/thu hồi/i, { timeout: 10000 });
});

test('approve dialog — Esc key closes it', async ({ page }) => {
  const id = await injectFinding('HIGH');
  await loginViaUI(page, 'security_lead');

  await page.fill('[data-testid="chat-input"]', `/approve ${id}`);
  await page.keyboard.press('Enter');
  await expect(page.locator('text=Phê duyệt Finding')).toBeVisible({ timeout: 5000 });

  await page.keyboard.press('Escape');
  await expect(page.locator('text=Phê duyệt Finding')).not.toBeVisible({ timeout: 3000 });
});
