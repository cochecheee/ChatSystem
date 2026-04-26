import { Page, request } from '@playwright/test';

const API = 'http://localhost:8001';

export async function resetTestDb() {
  const ctx = await request.newContext();
  await ctx.post(`${API}/test/reset`);
  await ctx.dispose();
}

export async function injectFinding(severity = 'HIGH', ruleId = 'test-sqli') {
  const ctx = await request.newContext();
  const res = await ctx.post(`${API}/test/inject-finding`, {
    data: { severity, rule_id: ruleId, message: `${severity} finding from E2E test` },
  });
  const body = await res.json();
  await ctx.dispose();
  return body.id as number;
}

export async function getToken(page: Page, role = 'security_lead') {
  const res = await page.request.post(`${API}/api/chat/auth/token`, {
    data: { username: `e2e_${role}`, role },
  });
  const body = await res.json();
  return body.access_token as string;
}

export async function loginViaUI(page: Page, role = 'security_lead') {
  await page.goto('/');
  await page.click('[data-nav="chat"]');

  await page.fill('input[placeholder="alice"]', `e2e_${role}`);
  await page.selectOption('select', role);
  await page.click('button:has-text("Đăng nhập")');
  await page.waitForSelector('button:has-text("Đăng xuất")', { timeout: 5000 });
}
