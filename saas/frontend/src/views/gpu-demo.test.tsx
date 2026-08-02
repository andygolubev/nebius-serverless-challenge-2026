import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../App";
import { JobDetail } from "./JobDetail";
import { Showcase, ShowcaseDetail } from "./Showcase";

const showcaseIds = [
  "g1-rough-terrain",
  "go1-walker",
  "ant-explorer",
  "halfcheetah-sprint",
  "hopper-balance",
  "walker2d-stride",
  "reacher-target",
];

const labels: Record<string, string> = {
  "go1-walker": "Go1 Walker",
  "ant-explorer": "Ant Explorer",
  "halfcheetah-sprint": "HalfCheetah Sprint",
  "hopper-balance": "Hopper Balance",
  "walker2d-stride": "Walker2D Stride",
  "g1-rough-terrain": "G1 Rough Terrain",
  "reacher-target": "Reacher Target",
};

const entry = (id: string) => ({
  id,
  label: labels[id],
  task: "Walk forward",
  description: `Story for ${labels[id]}`,
  avatar: `/avatars/${id}.svg`,
  expected_result: "A replayable trained policy",
  backend_label: id === "go1-walker" || id === "g1-rough-terrain" ? "MJX / JAX PPO" : "SB3 PPO",
  hardware_label: id === "go1-walker" ? "NVIDIA H100" : "CPU D3 · 8 vCPU",
  observed_duration: "Observed about 12 min",
  observed_cost: "Measured $0.12",
  acceptance_revision: "gallery-v1",
  executed_config: {
    environment: id,
    environment_label: labels[id],
    algorithm_label: "SB3 PPO",
    total_timesteps: 1_000_000,
    platform: "cpu-d3",
    preset: "8vcpu-32gb",
  },
  evaluation: { success: true, criterion: "mean reward ≥ 1000", primary_metric: "Mean reward" },
  has_media: true,
});

const showcaseEntries = { examples: showcaseIds.map(entry) };

const showcaseDetail = {
  ...entry("hopper-balance"),
  status: "completed",
  metrics: {
    aggregate: { episodes: 2, mean_reward: 31.581, success_rate: 1 },
    benchmark: { currency: "USD", estimated_cost: 0.5327 },
    checkpoint: "final-000102400000.zip",
    environment: "Hopper-v5",
    runtime_seconds: 650.1,
  },
  artifacts: [
    { id: "video_mid", name: "Video Mid", kind: "video", content_type: "video/mp4", size_bytes: 100, url: "/showcase/hopper-balance/artifacts/video_mid", download_url: "/showcase/hopper-balance/artifacts/video_mid?download=true" },
    { id: "video_final", name: "Video Final", kind: "video", content_type: "video/mp4", size_bytes: 123, url: "/showcase/hopper-balance/artifacts/video_final", download_url: "/showcase/hopper-balance/artifacts/video_final?download=true" },
    { id: "policy_bundle", name: "Policy Bundle", kind: "file", content_type: "application/zip", size_bytes: 456, url: "/showcase/hopper-balance/artifacts/policy_bundle", download_url: "/showcase/hopper-balance/artifacts/policy_bundle?download=true" },
  ],
};

function json(value: unknown, status = 200) {
  return Promise.resolve(new Response(JSON.stringify(value), { status, headers: { "Content-Type": "application/json" } }));
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  localStorage.clear();
});

describe("public showcase", () => {
  it("renders at the app root with no session and never shows a login wall", async () => {
    const fetchMock = vi.fn(() => json(showcaseEntries));
    vi.stubGlobal("fetch", fetchMock);
    render(<App />);

    expect(await screen.findByRole("heading", { name: "Watch robots learn to move" })).toBeVisible();
    expect(screen.queryByLabelText("Email")).not.toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "Sign in" })).not.toBeInTheDocument();
    // Authenticated-only navigation is absent for a visitor.
    expect(screen.queryByRole("button", { name: "Jobs" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "My Robots" })).not.toBeInTheDocument();
    // The public read carries no Authorization header.
    expect(fetchMock).toHaveBeenCalledWith("/showcase");
  });

  it("renders compact cards in server order with accessible local avatars and evidence facts", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(showcaseEntries)));
    const { container } = render(
      <Showcase authed={false} onSignIn={() => undefined} onOpenExample={() => undefined} />,
    );
    await screen.findByRole("button", { name: /G1 Rough Terrain/ });
    const cards = Array.from(container.querySelectorAll<HTMLButtonElement>(".gallery-card"));
    expect(cards.map((card) => card.getAttribute("aria-label"))).toEqual(
      showcaseIds.map((id) => `${labels[id]} — Walk forward`),
    );
    for (const id of showcaseIds) {
      const avatar = container.querySelector(`img[src="/avatars/${id}.svg"]`);
      expect(avatar).toBeInTheDocument();
      expect(avatar).toHaveAttribute("alt", "");
    }
    expect(screen.getAllByText("mean reward ≥ 1000")).toHaveLength(showcaseIds.length);
    expect(screen.queryByText("Observed about 12 min")).not.toBeInTheDocument();
    expect(screen.queryByText("Measured $0.12")).not.toBeInTheDocument();
    expect(screen.queryByText("1,000,000")).not.toBeInTheDocument();
    expect(screen.queryByText("A replayable trained policy")).not.toBeInTheDocument();
  });

  it("presents the challenge story, pipeline, evidence bands, and final train-your-own poster", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(showcaseEntries)));
    render(<Showcase authed={false} onSignIn={() => undefined} onOpenExample={() => undefined} />);
    expect(await screen.findByText("Verified training runs · Nebius Serverless Challenge 2026")).toBeVisible();
    expect(screen.getByRole("heading", { name: "Watch robots learn to move" })).toBeVisible();
    expect(screen.getByText("Simulate")).toBeVisible();
    expect(screen.getByText("Train")).toBeVisible();
    expect(screen.getByText("Keep")).toBeVisible();
    expect(screen.getByText("What every run leaves behind")).toBeVisible();
    expect(screen.getByText("Built with passion and love")).toBeVisible();
    expect(screen.getByText("Bring your own robot.")).toBeVisible();
    expect(screen.getByRole("button", { name: "Sign in to train →" })).toBeVisible();
  });

  it("offers no control that starts, re-runs, or queues a showcase example", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(showcaseEntries)));
    render(<Showcase authed onSignIn={() => undefined} onOpenExample={() => undefined} />);
    await screen.findByRole("button", { name: /Go1 Walker/ });
    for (const forbidden of [/^start training$/i, /^start$/i, /re-?run/i, /retrain/i, /queue/i, /^submit$/i]) {
      expect(screen.queryByRole("button", { name: forbidden })).not.toBeInTheDocument();
      expect(screen.queryByRole("link", { name: forbidden })).not.toBeInTheDocument();
    }
    // A signed-in visitor sees no sign-in prompt either — just read-only evidence.
    expect(screen.queryByRole("button", { name: /sign in/i })).not.toBeInTheDocument();
  });

  it("shows a designed empty state when no curated run has been published", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ examples: [] })));
    render(<Showcase authed={false} onSignIn={() => undefined} onOpenExample={() => undefined} />);
    expect(await screen.findByRole("heading", { name: "Verified runs are being prepared" })).toBeVisible();
    expect(screen.queryByRole("button", { name: /^Start training$/i })).not.toBeInTheDocument();
    // The empty state is a designed state, not an error or a spinner.
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(document.querySelector(".skeleton")).not.toBeInTheDocument();
    expect(screen.getByText("Bring your own robot.")).toBeVisible();
  });

  it("routes the sign-in call to action to login", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(showcaseEntries)));
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: "Sign in to train your own" }));
    expect(await screen.findByLabelText("Email")).toBeVisible();
    // Login is escapable: the visitor can return to the public showcase.
    fireEvent.click(screen.getByRole("button", { name: "← Back to verified runs" }));
    expect(await screen.findByRole("heading", { name: "Watch robots learn to move" })).toBeVisible();
  });

  it("opens a card into the read-only detail view", async () => {
    vi.stubGlobal("fetch", vi.fn((input: RequestInfo | URL) =>
      String(input) === "/showcase" ? json(showcaseEntries) : json(showcaseDetail),
    ));
    render(<App />);
    fireEvent.click(await screen.findByRole("button", { name: /Hopper Balance/ }));
    expect(await screen.findByRole("heading", { name: "Hopper Balance" })).toBeVisible();
    expect(screen.getByText("Walk forward — Story for Hopper Balance")).toBeVisible();
    expect(screen.getByText("Observed about 12 min")).toBeVisible();
    expect(screen.getByText("Measured $0.12")).toBeVisible();
  });

  it("routes shared footer links to public About and Terms views", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(showcaseEntries)));
    render(<App />);
    await screen.findByRole("heading", { name: "Watch robots learn to move" });

    document.documentElement.scrollTop = 500;
    fireEvent.click(screen.getByRole("button", { name: "About me" }));
    expect(screen.getByRole("heading", { name: "Andy Golubev" })).toBeVisible();
    await waitFor(() => expect(document.documentElement.scrollTop).toBe(0));
    expect(screen.getAllByRole("link", { name: "LinkedIn" })[0]).toHaveAttribute("rel", "noreferrer");
    expect(screen.getByRole("link", { name: "GitHub repository" })).toHaveAttribute("target", "_blank");

    document.documentElement.scrollTop = 500;
    fireEvent.click(screen.getByRole("button", { name: "Terms of use" }));
    expect(screen.getByRole("heading", { name: "The short version" })).toBeVisible();
    await waitFor(() => expect(document.documentElement.scrollTop).toBe(0));
    expect(screen.getByRole("heading", { name: "Download your results early" })).toBeVisible();
    expect(screen.getByText(/Files can disappear when the project ends or before that/)).toBeVisible();
    expect(screen.getByText("Last updated 2 August 2026 · Andy Golubev")).toBeVisible();
  });

  it("plays and switches rollout media, and gates the bundle behind the simulator disclosure", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json(showcaseDetail)));
    const confirm = vi.spyOn(window, "confirm").mockReturnValue(false);
    const { container } = render(
      <ShowcaseDetail exampleId="hopper-balance" authed={false} onBack={() => undefined} onSignIn={() => undefined} />,
    );

    // Final rollout is primary, and seeking works without a full download.
    await waitFor(() =>
      expect(container.querySelector("video")).toHaveAttribute("src", "/showcase/hopper-balance/artifacts/video_final"),
    );
    expect(container.querySelector("video")).toHaveAttribute("preload", "metadata");
    expect((await screen.findAllByText("31.58"))[0]).toBeVisible();

    // Progression media is selectable by human-readable label.
    fireEvent.click(screen.getByRole("radio", { name: /Video Mid/ }));
    expect(container.querySelector("video")).toHaveAttribute("src", "/showcase/hopper-balance/artifacts/video_mid");

    // Media failure degrades to a readable state with retry.
    fireEvent.error(container.querySelector("video")!);
    expect(screen.getByRole("button", { name: "Retry playback" })).toBeVisible();

    expect(screen.getByText(/Simulator-only policy/)).toBeVisible();
    fireEvent.click(screen.getByRole("link", { name: "Download policy bundle" }));
    expect(confirm).toHaveBeenCalledOnce();
  });

  it("reports an unmet task threshold without implying success or failure of the run", async () => {
    vi.stubGlobal("fetch", vi.fn(() =>
      json({ ...showcaseDetail, evaluation: { ...showcaseDetail.evaluation, success: false } }),
    ));
    render(
      <ShowcaseDetail exampleId="hopper-balance" authed={false} onBack={() => undefined} onSignIn={() => undefined} />,
    );
    expect(await screen.findByText("Below task threshold")).toBeVisible();
    // Infrastructure completion is stated separately.
    expect(screen.getByText("Artifacts ready")).toBeVisible();
  });

  it("shows a safe message for an unpublished or unknown example", async () => {
    vi.stubGlobal("fetch", vi.fn(() => json({ detail: "example not found" }, 404)));
    render(
      <ShowcaseDetail exampleId="ghost" authed={false} onBack={() => undefined} onSignIn={() => undefined} />,
    );
    expect(await screen.findByText("This run is not available in the showcase.")).toBeVisible();
  });
});

describe("job results", () => {
  beforeEach(() => {
    localStorage.setItem("sim2policy.session", "test-token");
  });

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

  it("keeps the chosen light token contract, Archivo fallback, and result breakpoints", async () => {
    // The application tsconfig intentionally omits Node types; Vitest itself runs in Node.
    // @ts-expect-error -- test-only runtime import, never bundled into the application.
    const { readFileSync } = await import("node:fs");
    const cwd = (globalThis as unknown as { process: { cwd: () => string } }).process.cwd();
    const stylesheet = readFileSync(`${cwd}/src/styles.css`, "utf8") as string;
    const index = readFileSync(`${cwd}/index.html`, "utf8") as string;
    expect(stylesheet).not.toContain("@media (prefers-color-scheme: dark)");
    expect(stylesheet).toContain("--grad-action:");
    expect(stylesheet).toContain("--grad-poster:");
    expect(stylesheet).toContain('--font: "Archivo", system-ui');
    expect(index).toContain("family=Archivo:wght@400;500;600;700;800");
    expect(stylesheet).toContain("@media (max-width: 900px)");
    expect(stylesheet).toContain("@media (max-width: 640px)");
    expect(stylesheet).toContain("@media (max-width: 390px)");
  });
});
