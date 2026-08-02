import { defineConfig, devices } from "@playwright/test";

const deployed = Boolean(process.env.SAAS_SMOKE_BASE_URL);
const evidenceRoot = "../../.form-validation-runs/playwright";

export default defineConfig({
  testDir: "./e2e",
  testMatch: deployed ? /deployed-smoke\.spec\.ts/ : /local-my-robots\.spec\.ts/,
  fullyParallel: !deployed,
  workers: deployed ? 1 : 2,
  timeout: deployed && process.env.SAAS_SMOKE_REMOTE_TRAINING === "true" ? 70 * 60_000 : deployed ? 15 * 60_000 : 45_000,
  expect: { timeout: deployed ? 20_000 : 8_000 },
  outputDir: `${evidenceRoot}/test-results`,
  reporter: [
    ["list"],
    ["junit", { outputFile: `${evidenceRoot}/browser.xml` }],
  ],
  use: {
    baseURL: process.env.SAAS_SMOKE_BASE_URL ?? "http://127.0.0.1:5173",
    screenshot: "only-on-failure",
    trace: deployed ? "off" : "retain-on-failure",
    video: "off",
  },
  webServer: deployed
    ? undefined
    : [
        {
          command:
            "cd ../backend && SAAS_VALIDATION_LOCAL=1 SAAS_VALIDATION_WORKERS=4 python -m validation_suite.local_server",
          url: "http://127.0.0.1:8000/health",
          timeout: 120_000,
          reuseExistingServer: false,
        },
        {
          command: "npm run dev -- --host 127.0.0.1 --port 5173",
          url: "http://127.0.0.1:5173",
          timeout: 120_000,
          reuseExistingServer: false,
        },
      ],
  projects: [
    {
      name: "chromium",
      use: { ...devices["Desktop Chrome"] },
    },
  ],
});
