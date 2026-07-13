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
  it("renders nested metrics and selectable playable video", async () => {
    const job = { id: "job1", preset: "go1-mjx-quality", environment: "go1", algorithm: "ppo-mjx", resolved_config: { environment: "go1", algorithm: "ppo-mjx", params: {} }, status: "completed", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), artifacts_status: "ready" };
    const artifacts = { job_id: "job1", status: "completed", metrics: { aggregate: { reward: 28.4 } }, media: [], artifacts: [{ id: "video_final", name: "Final", kind: "video", content_type: "video/mp4", size_bytes: 123, url: "https://objects.example/final.mp4", download_url: "https://objects.example/final.mp4?download=1" }] };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input).endsWith("/artifacts") ? json(artifacts) : json(job)));
    const { container } = render(<JobDetail jobId="job1" onBack={() => undefined} />);
    expect(await screen.findByText(/"reward": 28.4/)).toBeVisible();
    await waitFor(() => expect(container.querySelector("video")).toHaveAttribute("src", artifacts.artifacts[0].url));
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("href", artifacts.artifacts[0].download_url);
  });

  it("shows finalization and sanitized failure states", async () => {
    const failed = { id: "job2", preset: "go1-mjx-quick", environment: "go1", algorithm: "ppo-mjx", resolved_config: { environment: "go1", algorithm: "ppo-mjx", params: {} }, status: "failed", created_at: new Date().toISOString(), updated_at: new Date().toISOString(), artifacts_status: "pending", failure_phase: "submission", error: "quota unavailable" };
    vi.stubGlobal("fetch", vi.fn(() => json(failed)));
    render(<JobDetail jobId="job2" onBack={() => undefined} />);
    expect(await screen.findByText(/Failed during submission/)).toBeVisible();
    expect(screen.getByText(/quota unavailable/)).toBeVisible();
  });
});
