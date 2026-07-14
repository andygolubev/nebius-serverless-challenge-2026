import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Composer } from "./Composer";
import { JobDetail } from "./JobDetail";

const catalog = {
  gallery_enabled: false,
  examples: [],
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

const galleryIds = ["go1-walker", "ant-explorer", "halfcheetah-sprint", "hopper-balance", "walker2d-stride", "g1-rough-terrain", "reacher-target"];
const galleryCatalog = {
  ...catalog,
  gallery_enabled: true,
  examples: galleryIds.map((id) => {
    const labels: Record<string, string> = {
      "go1-walker": "Go1 Walker", "ant-explorer": "Ant Explorer", "halfcheetah-sprint": "HalfCheetah Sprint",
      "hopper-balance": "Hopper Balance", "walker2d-stride": "Walker2D Stride", "g1-rough-terrain": "G1 Rough Terrain",
      "reacher-target": "Reacher Target",
    };
    return {
      id, label: labels[id], task: "Train a task", description: `Story for ${labels[id]}`,
      avatar: `/avatars/${id}.svg`, expected_result: "A replayable trained policy", environment: id,
      algorithm: id === "go1-walker" || id === "g1-rough-terrain" ? "ppo-mjx" : "ppo-sb3",
      backend_label: id === "go1-walker" || id === "g1-rough-terrain" ? "MJX / JAX PPO" : "SB3 PPO",
      hardware_label: id === "go1-walker" ? "NVIDIA H100" : "CPU D3 · 8 vCPU",
      recommended_profile: id === "go1-walker" ? "go1-mjx-quality" : `${id}-v1`,
      recommended_params: { total_timesteps: 1000, seed: 0 },
      optional_params: [{ name: "seed", label: "Seed", type: "int", default: 0, min: 0, max: 2147483647 }],
      observed_duration: "Measured 12 min", observed_cost: "Measured $0.12", success_criterion: "mean reward ≥ 1000",
      primary_metric: "Mean reward", acceptance_revision: "gallery-v1",
      workload_profiles: id === "go1-walker" ? [
        { id: "go1-mjx-quick", label: "Go1 Quick", recommended: false, params: { total_timesteps: 5_000_000 } },
        { id: "go1-mjx-standard", label: "Go1 Standard", recommended: false, params: { total_timesteps: 25_000_000 } },
        { id: "go1-mjx-quality", label: "Go1 Quality", recommended: true, params: { total_timesteps: 100_000_000 } },
      ] : [],
    };
  }),
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

describe("verified examples gallery", () => {
  it("renders exactly seven local-avatar cards with no global backend or hardware selector", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(galleryCatalog)));
    render(<Composer onSubmitted={() => undefined} />);
    const group = await screen.findByRole("radiogroup", { name: "Verified training examples" });
    expect(screen.getAllByRole("radio")).toHaveLength(7);
    for (const id of galleryIds) {
      const image = group.querySelector(`img[src="/avatars/${id}.svg"]`);
      expect(image).toBeInTheDocument();
    }
    expect(screen.queryByLabelText(/^Backend$/)).not.toBeInTheDocument();
    expect(screen.queryByLabelText(/^Hardware$/)).not.toBeInTheDocument();
  });

  it("selects the measured passing Go1 Quality workload as the recommendation", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(galleryCatalog)));
    render(<Composer onSubmitted={() => undefined} />);
    fireEvent.click(await screen.findByRole("radio", { name: /Go1 Walker/ }));
    expect(screen.getByLabelText("Workload size")).toHaveValue("go1-mjx-quality");
    expect(screen.getByRole("option", { name: /Go1 Quality · recommended/ })).toBeVisible();
  });

  it("reviews and submits only the selected example, fixed profile, and seed", async () => {
    const fetchMock = vi.fn((_input: RequestInfo | URL, init?: RequestInit) =>
      init?.method === "POST"
        ? json({ id: "job", status: "queued" }, 201)
        : json(galleryCatalog),
    );
    vi.stubGlobal("fetch", fetchMock);
    const submitted = vi.fn();
    render(<Composer onSubmitted={submitted} />);
    fireEvent.click(await screen.findByRole("radio", { name: /Hopper Balance/ }));
    expect(screen.getAllByRole("heading", { name: /Hopper Balance/ })).toHaveLength(2);
    expect(screen.getByText("Recommended and fixed")).toBeVisible();
    fireEvent.change(screen.getByLabelText("Seed"), { target: { value: "17" } });
    fireEvent.click(screen.getByRole("button", { name: "Start training" }));
    await waitFor(() => expect(submitted).toHaveBeenCalledOnce());
    const request = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
    expect(JSON.parse(String(request[1]?.body))).toEqual({
      gallery_example_id: "hopper-balance",
      gallery_profile_id: "hopper-balance-v1",
      params: { seed: 17 },
    });
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
    const video = container.querySelector("video")!;
    const play = vi.spyOn(video, "play").mockResolvedValue(undefined);
    const pause = vi.spyOn(video, "pause").mockImplementation(() => undefined);
    fireEvent.click(screen.getByRole("button", { name: "Play rollout" }));
    expect(play).toHaveBeenCalledOnce();
    fireEvent.play(video);
    expect(screen.getByRole("button", { name: "Pause rollout" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Pause rollout" }));
    expect(pause).toHaveBeenCalledOnce();
    fireEvent.pause(video);
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

  it("shows compact custom provenance, honest threshold, and bundle disclosure", async () => {
    const job = {
      id: "custom-job", preset: null, environment: "uploaded-biped", algorithm: "ppo-sb3",
      resolved_config: {
        robot: { id: "robot-1", name: "Buddy", robot_type: "biped", digest: "a".repeat(64) },
        setup: { id: "setup-1", name: "Buddy walk", task_template_id: "walk-forward", scene_preset_id: "ramp-course" },
        training: { platform: "cpu-d3", preset: "8vcpu-32gb", version: "custom-ppo-quick-v1" },
      },
      status: "completed", created_at: new Date().toISOString(), updated_at: new Date().toISOString(),
      artifacts_status: "ready", job_kind: "custom-robot", preparation_fingerprint: "f".repeat(64),
    };
    const artifacts = {
      job_id: job.id, status: "completed", media: [],
      metrics: { aggregate: { mean_reward: 18.2, success_rate: 0.6, task_threshold_achieved: false }, simulator_only: true },
      artifacts: [
        { id: "video_final", name: "Final rollout", kind: "video", content_type: "video/mp4", size_bytes: 123, url: "/video", download_url: "/video?download=1" },
        { id: "policy_bundle", name: "Simulator policy bundle", kind: "file", content_type: "application/zip", size_bytes: 456, url: "/bundle", download_url: "/bundle?download=1" },
      ],
    };
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) => String(input).endsWith("/artifacts") ? json(artifacts) : json(job)));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<JobDetail jobId={job.id} onBack={() => undefined} />);
    expect(await screen.findByText(/Simulator-only policy/)).toBeVisible();
    expect(screen.getByText("Below task threshold")).toBeVisible();
    expect(screen.getByRole("heading", { name: /Buddy · walk forward/ })).toBeVisible();
    fireEvent.click(screen.getByText(/custom-ppo-quick · CPU/));
    expect(screen.getByText(/cpu-d3 · 8vcpu-32gb/)).toBeVisible();
    const bundle = screen.getByRole("link", { name: "Download policy bundle" });
    fireEvent.click(bundle);
    expect(confirm).toHaveBeenCalledOnce();
    expect(screen.queryByText("GPU utilization")).not.toBeInTheDocument();
  });

  it("keeps dark-mode tokens and all result breakpoints in the shipped stylesheet", async () => {
    // The application tsconfig intentionally omits Node types; Vitest itself runs in Node.
    // @ts-expect-error -- test-only runtime import, never bundled into the application.
    const { readFileSync } = await import("node:fs");
    const cwd = (globalThis as unknown as { process: { cwd: () => string } }).process.cwd();
    const stylesheet = readFileSync(`${cwd}/src/styles.css`, "utf8") as string;
    expect(stylesheet).toContain("@media (prefers-color-scheme: dark)");
    for (const token of ["--bg", "--surface", "--surface-2", "--border", "--text", "--text-muted", "--accent", "--focus-ring"]) {
      expect(stylesheet.match(new RegExp(`${token}:`, "g"))).toHaveLength(2);
    }
    expect(stylesheet).toContain("@media (max-width: 900px)");
    expect(stylesheet).toContain("@media (max-width: 640px)");
    expect(stylesheet).toContain("@media (max-width: 390px)");
  });
});
