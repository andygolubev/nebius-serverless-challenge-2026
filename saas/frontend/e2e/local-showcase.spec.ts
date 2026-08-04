import { expect, test } from "@playwright/test";

const entry = {
  id: "hopper-balance",
  label: "Hopper Balance",
  task: "Walk forward",
  description: "Train a hopper to move without falling.",
  avatar: "/avatars/hopper-balance.svg",
  expected_result: "A replayable trained policy",
  backend_label: "SB3 PPO",
  hardware_label: "CPU D3 · 8 vCPU",
  observed_duration: "Observed about 12 min",
  observed_cost: "Measured $0.12",
  acceptance_revision: "gallery-v1",
  executed_config: {
    environment: "Hopper-v5",
    environment_label: "Hopper-v5",
    algorithm_label: "SB3 PPO",
    total_timesteps: 1_000_000,
    platform: "cpu-d3",
    preset: "8vcpu-32gb",
  },
  evaluation: {
    success: false,
    criterion: "mean reward ≥ 1000",
    primary_metric: "Mean reward",
  },
  has_media: true,
};

const detail = {
  ...entry,
  status: "completed",
  metrics: {
    aggregate: { episodes: 2, mean_reward: 31.58, success_rate: 0 },
    checkpoint: "final-000102400000.zip",
    environment: "Hopper-v5",
    runtime_seconds: 650.1,
  },
  artifacts: [
    {
      id: "video_final",
      name: "Final rollout",
      kind: "video",
      content_type: "video/mp4",
      size_bytes: 123,
      url: "/showcase/hopper-balance/artifacts/video_final",
      download_url: "/showcase/hopper-balance/artifacts/video_final?download=true",
    },
    {
      id: "policy_bundle",
      name: "Policy bundle",
      kind: "file",
      content_type: "application/zip",
      size_bytes: 456,
      url: "/showcase/hopper-balance/artifacts/policy_bundle",
      download_url: "/showcase/hopper-balance/artifacts/policy_bundle?download=true",
    },
  ],
};

test("[browser:showcase] omits threshold badges and detail KPIs while retaining result evidence", async ({ page }) => {
  await page.route("**/showcase", (route) => route.fulfill({ json: { examples: [entry] } }));
  await page.route("**/showcase/hopper-balance", (route) => route.fulfill({ json: detail }));

  await page.goto("/");
  const card = page.getByRole("button", { name: "Hopper Balance — Walk forward" });
  await expect(card).toBeVisible();
  await expect(card.getByText(/task threshold/i)).toHaveCount(0);

  await card.click();
  await expect(page.getByRole("heading", { name: "Hopper Balance" })).toBeVisible();
  await expect(page.getByText("Artifacts ready")).toBeVisible();
  await expect(page.getByText("Success criterion")).toBeVisible();
  await expect(page.getByText("Observed duration")).toBeVisible();
  await expect(page.getByRole("link", { name: "Download policy bundle" })).toBeVisible();
  await expect(page.locator(".showcase-detail .kpi-grid")).toHaveCount(0);
  await expect(page.getByText(/task threshold/i)).toHaveCount(0);
  await expect(page.getByText("Evaluation", { exact: true })).toBeVisible();
  await expect(page.locator(".configuration-details")).toBeVisible();
});
