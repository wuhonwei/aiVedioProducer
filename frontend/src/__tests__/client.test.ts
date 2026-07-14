import { describe, it, expect, vi } from "vitest";
import { createProject } from "../api/client";

describe("api client", () => {
  it("posts project", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: "p1", name: "测" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const p = await createProject("测");
    expect(p.id).toBe("p1");
    expect(fetchMock).toHaveBeenCalled();
  });
});
