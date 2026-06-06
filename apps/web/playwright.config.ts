import { defineConfig } from "@playwright/test";

const reuseExistingServer =
  process.env.E2E_REUSE_EXISTING_SERVER === "true" ||
  process.env.npm_lifecycle_event === "test:e2e:reuse";

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: { timeout: 10_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  reporter: "list",
  use: {
    baseURL: process.env.E2E_BASE_URL || "http://localhost:3001",
    trace: "on-first-retry",
    viewport: { width: 1280, height: 720 },
  },
  webServer: process.env.E2E_BASE_URL
    ? undefined
    : {
        command: "npx next dev -p 3001",
        port: 3001,
        reuseExistingServer,
        timeout: 60_000,
      },
});
