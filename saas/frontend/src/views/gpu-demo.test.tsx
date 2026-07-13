import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";
import { JobDetail } from "./JobDetail";

const catalog = {
  environments: [{ id: "go1", label: "Go1", description: "GPU quadruped", algorithms: ["ppo-mjx"] }],
  algorithms: [{ id: "ppo-mjx", label: "PPO (MJX / JAX)", description: "GPU PPO", params: [
    { name: "total_timesteps", label: "Total timesteps", type: "int", default: 100_000_000, min: 10_000, max: 100_000_000 },
    { name: "learning_rate", label: "Learning rate", type: "float", default: 0.0003, min: 0.00001, max: 0.01 },
    { name: "seed", label: "Seed", type: "int", default: 0, min: 0, max: 2147483647 },
  ] }],
  presets: [
    { id: "go1-mjx-quick", label: "Go1 Quick", description: "Fast GPU demo", default: false, environment: "go1", algorithm: "ppo-mjx", params: { total_timesteps: 5_000_000 } },
    { id: "go1-mjx-standard", label: "Go1 Standard", description: "Balanced GPU run", default: true, environment: "go1", algorithm: "ppo-mjx", params: { total_timesteps: 25_000_000 } },
    { id: "go1-mjx-quality", label: "Go1 Quality", description: "Flagship GPU result", default: false, environment: "go1", algorithm: "ppo-mjx", params: { total_timesteps: 100_000_000 } },
  ],
};

function json(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }));
}

beforeEach(() => {
  localStorage.setItem("sim2policy.session", "test-token");
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("GPU composer", () => {
  it("shows exactly the three GPU workloads and no SB3 option", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(catalog)));
    render(<Composer onSubmitted={() => undefined} />);
    const group = await screen.findByRole("radiogroup", { name: "GPU workload" });
    expect(group).toHaveTextContent("Go1 Quick");
    expect(group).toHaveTextContent("Go1 Standard");
    expect(group).toHaveTextContent("Go1 Quality");
    expect(group).not.toHaveTextContent("SB3");
    expect(screen.getByRole("radio", { name: /Go1 Standard/ })).toHaveAttribute("aria-checked", "true");
  });

  it("keeps out-of-range submission disabled", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(catalog)));
    render(<Composer onSubmitted={() => undefined} />);
    const input = await screen.findByLabelText("Total timesteps");
    fireEvent.change(input, { target: { value: "100000001" } });
    expect(screen.getByRole("button", { name: "Start training" })).toBeDisabled();
  });
});

describe("job results", () => {
  it("renders formatted KPIs, semantic details, episodes, and selectable playable video", async () => {
    const job = { id: "job1", preset: "go1-mjx-quality", environment: "go1", algorithm: "ppo-mjx", resolved_config: { environment: "go1", algorithm: "ppo-mjx", params: {} }, status: "completed", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), artifacts_status: "ready" };
    const artifacts = { job_id: "job1", status: "completed", metrics: {
      aggregate: { episodes: 2, mean_reward: 31.581, std_reward: 2.036, success_rate: 1 },
      benchmark: { currency: "USD", estimated_cost: 0.5327, gpu_utilization_percent: 52 },
      checkpoint: "final-000102400000.zip",
      environment: "Go1JoystickFlatTerrain",
      episodes: [
        { index: 0, reward: 30.9, length: 1000, fell: false, mean_velocity: -0.013 },
        { index: 1, reward: 32.2, length: 1000, fell: false, mean_velocity: 0.018 },
      ],
      run_id: "121455e7fd974a2baf6dd49b80910adc3",
      runtime_seconds: 650.1,
    }, media: [], artifacts: [
      { id: "video_learning", name: "Learning rollout", kind: "video", content_type: "video/mp4", size_bytes: 100, url: "https://objects.example/learning.mp4", download_url: "https://objects.example/learning.mp4?download=1" },
      { id: "video_final", name: "Final rollout", kind: "video", content_type: "video/mp4", size_bytes: 123, url: "https://objects.example/final.mp4", download_url: "https://objects.example/final.mp4?download=1" },
    ] };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input).endsWith("/artifacts") ? json(artifacts) : json(job)));
    const { container } = render(<JobDetail jobId="job1" onBack={() => undefined} />);
    expect((await screen.findAllByText("31.58"))[0]).toBeVisible();
    expect(screen.getAllByText("$0.53")[0]).toBeVisible();
    expect(screen.getAllByText("52%")[0]).toBeVisible();
    expect(screen.getAllByText("10m 50s")[0]).toBeVisible();
    expect(screen.getAllByText("Go1JoystickFlatTerrain")[0]).toBeVisible();
    await waitFor(() => expect(container.querySelector("video")).toHaveAttribute("src", artifacts.artifacts[1].url));
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("href", artifacts.artifacts[1].download_url);
    fireEvent.error(container.querySelector("video")!);
    expect(screen.getByRole("button", { name: "Retry playback" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Retry playback" }));
    expect(screen.queryByRole("button", { name: "Retry playback" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Learning rollout/ }));
    expect(container.querySelector("video")).toHaveAttribute("src", artifacts.artifacts[0].url);

    fireEvent.click(container.querySelectorAll(".result-detail > summary")[1]);
    expect(screen.getAllByText("Completed")[0]).toBeVisible();
    expect(screen.getByText("-0.01")).toBeVisible();
    const raw = screen.getByText(/"mean_reward": 31.581/);
    expect(raw).not.toBeVisible();
  });

  it("keeps finalization visible", async () => {
    const finalizing = { id: "job-finalizing", preset: "go1-mjx-standard", environment: "go1", algorithm: "ppo-mjx", resolved_config: { environment: "go1", algorithm: "ppo-mjx", params: {} }, status: "finalizing", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), artifacts_status: "pending" };
    vi.stubGlobal("fetch", vi.fn(() => json(finalizing)));
    render(<JobDetail jobId="job-finalizing" onBack={() => undefined} />);
    expect(await screen.findByText(/Reports and playable media are being finalized/)).toBeVisible();
  });

  it("shows sanitized failure states", async () => {
    const failed = { id: "job2", preset: "go1-mjx-quick", environment: "go1", algorithm: "ppo-mjx", resolved_config: { environment: "go1", algorithm: "ppo-mjx", params: {} }, status: "failed", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), artifacts_status: "pending", failure_phase: "submission", error: "quota unavailable" };
    vi.stubGlobal("fetch", vi.fn(() => json(failed)));
    render(<JobDetail jobId="job2" onBack={() => undefined} />);
    expect(await screen.findByText(/Failed during submission/)).toBeVisible();
    expect(screen.getByText(/quota unavailable/)).toBeVisible();
  });

  it("handles missing optional metrics and completed results without media", async () => {
    const job = { id: "job3-with-a-very-long-id-that-must-wrap-safely", preset: null, environment: "go1", algorithm: "ppo-mjx", resolved_config: { environment: "go1", algorithm: "ppo-mjx", params: {} }, status: "completed", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), artifacts_status: "ready" };
    const artifacts = { job_id: job.id, status: "completed", metrics: { checkpoint: "final-checkpoint-with-an-extremely-long-name-that-must-not-create-a-column.zip" }, media: [], artifacts: [] };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input).endsWith("/artifacts") ? json(artifacts) : json(job)));
    render(<JobDetail jobId={job.id} onBack={() => undefined} />);
    expect(await screen.findByText("This completed run has metrics but no playable rollout media.")).toBeVisible();
    expect(screen.getAllByText("—").length).toBeGreaterThan(1);
    expect(screen.getAllByTitle(artifacts.metrics.checkpoint)[0]).toBeVisible();
    expect(document.querySelector(".metrics-grid")).not.toBeInTheDocument();
  });
});
