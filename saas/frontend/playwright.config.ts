import { defineConfig, devices } from "@playwright/test";

const deployed = Boolean(process.env.SAAS_SMOKE_BASE_URL);
const evidenceRoot = "../../.form-validation-runs/playwright";
const shardLabel = process.env.FORM_BROWSER_SHARD_LABEL ?? "local";

export default defineConfig({
  testDir: "./e2e",
  testMatch: deployed ? /deployed-smoke\.spec\.ts/ : /local-(my-robots|showcase)\.spec\.ts/,
  fullyParallel: !deployed,
  workers: 1,
  timeout: deployed && process.env.SAAS_SMOKE_REMOTE_TRAINING === "true" ? 70 * 60_000 : deployed ? 15 * 60_000 : 45_000,
  expect: { timeout: deployed ? 20_000 : 8_000 },
  outputDir: `${evidenceRoot}/test-results-${shardLabel}`,
  reporter: [
    ["list"],
    ["junit", { outputFile: `${evidenceRoot}/browser-${deployed ? "deployed" : shardLabel}.xml` }],
  ],
  use: {
    baseURL: process.env.SAAS_SMOKE_BASE_URL ?? "http://127.0.0.1:5173",
    screenshot: "only-on-failure",
    // Browser traces retain multipart request bodies, including uploaded private XML.
    // Screenshots and JUnit are sufficient sanitized failure evidence for this suite.
    trace: "off",
    video: "off",
  },
  webServer: deployed
    ? undefined
    : [
        {
          command:
            "cd ../backend && SAAS_VALIDATION_LOCAL=1 SAAS_VALIDATION_WORKERS=8 python -m validation_suite.local_server",
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
