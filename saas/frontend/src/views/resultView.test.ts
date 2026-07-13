import { describe, expect, it } from "vitest";
import { buildResultView, formatDuration, formatMetric, formatNumber } from "./resultView";

describe("type-aware result view", () => {
  it("extracts screenshot-shaped nested metrics with bounded formatting", () => {
    const metrics = {
      aggregate: { mean_reward: 31.58141655930881, success_rate: 0.95 },
      benchmark: { currency: "USD", estimated_cost: 0.5327323371779167 },
      checkpoint: "final-000102400000.zip",
      device: { gpu: { gpus: [{ name: "NVIDIA H100 80GB HBM3", utilization_percent: 52 }] } },
      environment: "Go1JoystickFlatTerrain",
      runtime_seconds: 650.114,
    };
    const view = buildResultView(metrics, "go1");
    expect(view.kpis.map((kpi) => kpi.value)).toEqual([
      "31.58",
      "95%",
      "10m 50s",
      "$0.53",
      "52%",
      "Go1JoystickFlatTerrain",
      "final-000102400000.zip",
    ]);
    expect(view.compute).toContainEqual(expect.objectContaining({ value: "NVIDIA H100 80GB HBM3" }));
  });

  it("derives success from episodes and handles missing optional values", () => {
    const view = buildResultView(
      { episodes: [{ fell: false }, { fell: true }, { success: true }], deeply: { nested: { unknown: { value: 4 } } } },
      "go1",
    );
    expect(view.kpis[1].value).toBe("66.67%");
    expect(view.kpis[0].value).toBe("—");
    expect(view.episodes).toHaveLength(3);
    expect(view.run).toHaveLength(0);
  });

  it("keeps a large episode set readable without turning it into raw metric columns", () => {
    const episodes = Array.from({ length: 75 }, (_, index) => ({ index, reward: index / 3, length: 1000, fell: index % 10 === 0 }));
    const view = buildResultView({ episodes }, "go1");
    expect(view.episodes).toHaveLength(75);
    expect(view.episodes[74]).toEqual(expect.objectContaining({ index: "74", length: "1,000" }));
    expect(view.evaluation).toHaveLength(0);
  });

  it("formats duration, numbers, cost, percentages, booleans, and arrays consistently", () => {
    expect(formatDuration(12.345)).toBe("12.35s");
    expect(formatDuration(3725)).toBe("1h 2m");
    expect(formatNumber(12345.678)).toBe("12,345.68");
    expect(formatMetric("estimated_cost", 1.237)).toBe("$1.24");
    expect(formatMetric("success_rate", 0.5)).toBe("50%");
    expect(formatMetric("available", true)).toBe("Yes");
    expect(formatMetric("names", ["a", "b"])).toBe("a, b");
  });
});
