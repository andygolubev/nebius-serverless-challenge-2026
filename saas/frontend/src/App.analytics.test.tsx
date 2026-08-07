import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

const { trackView } = vi.hoisted(() => ({ trackView: vi.fn() }));
vi.mock("./analytics", () => ({ trackView }));

import { App } from "./App";

describe("App analytics", () => {
  beforeEach(() => {
    trackView.mockReset();
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ examples: [] }) }));
  });

  it("tracks initial and changed SPA views exactly once with their route data", async () => {
    render(<App />);
    await waitFor(() => expect(trackView).toHaveBeenCalledWith("showcase", undefined));
    fireEvent.click(screen.getByRole("button", { name: "About me" }));
    await waitFor(() => expect(trackView).toHaveBeenLastCalledWith("about", undefined));
    expect(trackView).toHaveBeenCalledTimes(2);
  });
});
