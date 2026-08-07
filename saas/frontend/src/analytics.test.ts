import { beforeEach, describe, expect, it, vi } from "vitest";

describe("trackView", () => {
  beforeEach(() => {
    vi.resetModules();
    sessionStorage.clear();
  });

  it("posts one anonymous keepalive beacon and ignores rejection", async () => {
    const fetchMock = vi.fn().mockRejectedValue(new Error("blocked"));
    vi.stubGlobal("fetch", fetchMock);
    const { trackView } = await import("./analytics");
    expect(() => trackView("showcase-example", "g1-rough")).not.toThrow();
    await Promise.resolve();
    expect(fetchMock).toHaveBeenCalledOnce();
    expect(fetchMock.mock.calls[0][0]).toBe("/analytics/collect");
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: "POST", keepalive: true });
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ view: "showcase-example", entity_id: "g1-rough" });
  });
});
