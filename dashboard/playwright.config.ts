import { defineConfig, devices } from '@playwright/test';

export default defineConfig({
  testDir: './tests/e2e',
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: false,
  retries: 0,

  use: {
    baseURL: 'http://localhost:5174',
    trace: 'on-first-retry',
  },

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],

  webServer: [
    {
      command: 'cross-env TEST_MODE=1 GEMINI_API_KEY=test-dummy ..\\mcp\\.venv\\Scripts\\uvicorn.exe src.main:app --port 8001 --app-dir ../mcp',
      url: 'http://localhost:8001/health',
      reuseExistingServer: !process.env.CI,
      timeout: 20_000,
    },
    {
      command: 'cross-env VITE_API_URL=http://localhost:8001 npm run dev -- --port 5174',
      url: 'http://localhost:5174',
      reuseExistingServer: !process.env.CI,
      timeout: 20_000,
    },
  ],
});
