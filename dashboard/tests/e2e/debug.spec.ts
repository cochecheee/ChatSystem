import { test, expect, Page } from '@playwright/test';

interface ConsoleError {
  type: string;
  text: string;
  location?: string;
}

function newErrorCollector(page: Page): ConsoleError[] {
  const errors: ConsoleError[] = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') {
      const loc = msg.location();
      errors.push({
        type: 'console.error',
        text: msg.text(),
        location: loc.url ? `${loc.url}:${loc.lineNumber}:${loc.columnNumber}` : undefined,
      });
    }
  });
  page.on('pageerror', (err) => {
    errors.push({ type: 'pageerror', text: `${err.name}: ${err.message}\n${err.stack ?? ''}` });
  });
  page.on('requestfailed', (req) => {
    errors.push({
      type: 'requestfailed',
      text: `${req.method()} ${req.url()} — ${req.failure()?.errorText}`,
    });
  });
  return errors;
}

const PAGES: { id: string; label: string }[] = [
  { id: 'overview', label: 'Overview' },
  { id: 'pipelines', label: 'Pipelines' },
  { id: 'vulns', label: 'Vulnerabilities' },
  { id: 'dast', label: 'DAST' },
  { id: 'sca', label: 'SCA' },
  { id: 'secrets', label: 'Secrets' },
  { id: 'repos', label: 'Repositories' },
  { id: 'chat', label: 'AI Chat' },
  { id: 'prbot', label: 'PR Bot' },
  { id: 'governance', label: 'Governance' },
  { id: 'reports', label: 'Reports' },
  { id: 'settings', label: 'Settings' },
];

// Errors này là known noise trong TEST_MODE (không có GitHub token, demo login chưa run, etc.)
const NOISE_PATTERNS = [
  /favicon/i,
  /HMR|hot-update/i,
  /\/github\/runs.*502/i, // GitHub API unavailable in TEST_MODE
  /Failed to load resource.*502/i, // 502 from upstream GitHub
  /Failed to load resource.*404/i, // missing endpoints in test env (e.g. unauthed /auth/me)
  /Failed to load resource.*401/i, // /auth/me before login
];

function isNoise(text: string): boolean {
  return NOISE_PATTERNS.some((re) => re.test(text));
}

for (const { id, label } of PAGES) {
  test(`page "${label}" loads without error`, async ({ page }) => {
    const errors = newErrorCollector(page);
    await page.goto('/');
    await page.waitForSelector('aside.sidebar', { timeout: 10_000 });

    if (id !== 'overview') {
      const navLocator = page.locator(`[data-nav="${id}"]`);
      await navLocator.waitFor({ timeout: 5_000 });
      await navLocator.click();
    }
    await page.waitForTimeout(1500); // settle: polling, fetch, render

    await page.screenshot({ path: `test-results/page-${id}.png`, fullPage: true });

    const real = errors.filter((e) => !isNoise(e.text));
    if (real.length > 0) {
      console.log(`\n=== Real errors on "${label}" ===`);
      for (const e of real) {
        console.log(`[${e.type}] ${e.text}${e.location ? ` @ ${e.location}` : ''}`);
      }
    }

    expect
      .soft(
        real,
        `Errors on "${label}":\n${real.map((e) => `  ${e.type}: ${e.text}${e.location ? ' @ ' + e.location : ''}`).join('\n')}`
      )
      .toEqual([]);
  });
}
