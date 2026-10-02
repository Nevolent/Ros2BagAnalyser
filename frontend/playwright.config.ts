import { defineConfig } from '@playwright/test';
const baseURL = process.env.PLAYWRIGHT_BASE_URL || 'http://127.0.0.1:5173';
export default defineConfig({
  testDir: './tests',
  use: {
    baseURL,
    colorScheme: 'dark',
    viewport: { width: 1440, height: 1000 },
    launchOptions: {
      executablePath: process.env.CHROMIUM_PATH,
    },
    trace: 'retain-on-failure',
  },
  webServer: process.env.PLAYWRIGHT_BASE_URL
    ? undefined
    : {
        command: 'npm run dev -- --port 5173 --strictPort',
        url: baseURL,
        reuseExistingServer: !process.env.CI,
      },
  reporter: 'list',
});
