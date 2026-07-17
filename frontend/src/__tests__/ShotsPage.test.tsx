import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ShotsPage } from "../pages/ShotsPage";
import * as api from "../api/client";

vi.mock("../api/client");

describe("ShotsPage", () => {
  beforeEach(() => {
    vi.mocked(api.getShots).mockResolvedValue({
      items: [
        {
          shot_id: "EP001_SC001_SH001",
          event_id: "event_0001",
          chapter_id: "chapter_0001",
          order: 1,
          shot_type: "medium",
          duration_sec: 4,
          visual_prompt: "推门",
          review_status: "needs_review",
          review: { status: "needs_review" },
          cast: ["林澈"],
          source_refs: [{ event_id: "event_0001", evidence: "血迹" }],
        },
      ],
      total_count: 1,
      has_more: false,
      schema_version: 2,
    });
    vi.mocked(api.getAssetPlan).mockResolvedValue({
      characters: [{ name: "林澈", shot_count: 1 }],
      locations: [],
    });
    vi.mocked(api.reviewShot).mockResolvedValue({});
    vi.mocked(api.patchShot).mockResolvedValue({});
    vi.mocked(api.exportShotsYaml).mockResolvedValue({ count: 1, root: "shots" });
    vi.mocked(api.regenerateAssetPlan).mockResolvedValue({});
  });

  it("filters by review status and can lock", async () => {
    render(<ShotsPage projectId="p1" />);
    expect(await screen.findByText("分镜脚本")).toBeInTheDocument();
    fireEvent.change(screen.getByLabelText("filter-review-status"), {
      target: { value: "approved" },
    });
    await waitFor(() => {
      expect(api.getShots).toHaveBeenCalledWith(
        "p1",
        expect.objectContaining({ reviewStatus: "approved" }),
      );
    });
    fireEvent.click(await screen.findByText(/EP001_SC001_SH001/));
    fireEvent.click(screen.getByRole("button", { name: "锁定" }));
    await waitFor(() => {
      expect(api.reviewShot).toHaveBeenCalledWith("p1", "EP001_SC001_SH001", {
        status: "locked",
      });
    });
  });
});
