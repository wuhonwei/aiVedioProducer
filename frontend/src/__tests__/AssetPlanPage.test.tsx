import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { AssetPlanPage } from "../pages/AssetPlanPage";
import * as api from "../api/client";

vi.mock("../api/client");

describe("AssetPlanPage", () => {
  beforeEach(() => {
    vi.mocked(api.getAssetPlan).mockResolvedValue({
      generated_from: { shot_review_status: "approved_only", shot_count: 1 },
      characters: [
        {
          id: "char_0001",
          name: "林澈",
          priority: "high",
          status: "pending",
          needs_lora: true,
          shot_ids: ["EP001_SC001_SH001"],
          shot_count: 1,
        },
      ],
      locations: [],
      props: [],
    });
    vi.mocked(api.regenerateAssetPlan).mockResolvedValue({});
    vi.mocked(api.patchAssetPlanEntry).mockResolvedValue({ status: "approved" });
  });

  it("lists assets and patches status", async () => {
    render(<AssetPlanPage projectId="p1" />);
    expect(await screen.findByText("资产计划")).toBeInTheDocument();
    expect(await screen.findByText(/林澈/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "标记通过" }));
    await waitFor(() => {
      expect(api.patchAssetPlanEntry).toHaveBeenCalledWith(
        "p1",
        "characters",
        "char_0001",
        { status: "approved" },
      );
    });
  });
});
