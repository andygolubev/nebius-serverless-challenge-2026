import { describe, expect, it } from "vitest";
import { formatCost, formatDuration } from "./Showcase";

// The showcase payload carries measured runtime and cost as raw numbers. Rendering
// them unformatted put "1038.543337257" and "0.8510285680300418" on the public page.
describe("showcase measurement formatting", () => {
  it("renders measured runtime in human units", () => {
    expect(formatDuration(1038.543337257)).toBe("17 min 19 s");
    expect(formatDuration(172.64614535099997)).toBe("2 min 53 s");
    expect(formatDuration(1772.2933810149998)).toBe("29 min 32 s");
    expect(formatDuration(45.2)).toBe("45 s");
    expect(formatDuration(7.25)).toBe("7.3 s");
    expect(formatDuration(3600)).toBe("1 h 0 min");
    expect(formatDuration(120)).toBe("2 min");
  });

  it("renders measured cost as currency without losing sub-cent runs", () => {
    expect(formatCost(0.8510285680300418)).toBe("$0.85");
    expect(formatCost(0.04194101059183644)).toBe("$0.04");
    // A real run cost less than a cent; "$0.00" would read as free.
    expect(formatCost(0.009514720899344)).toBe("<$0.01");
    expect(formatCost(0)).toBe("$0.00");
  });

  it("passes through a value it cannot interpret rather than showing NaN", () => {
    expect(formatDuration("not-a-number")).toBe("not-a-number");
    expect(formatCost("unknown")).toBe("unknown");
  });
});
