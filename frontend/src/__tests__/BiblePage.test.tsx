import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BiblePage } from "../pages/BiblePage";
import * as api from "../api/client";

vi.mock("../api/client");

describe("BiblePage", () => {
  beforeEach(() => {
    vi.mocked(api.getBible).mockResolvedValue({ logline: "自动", project_meta: { title: "T" } });
    vi.mocked(api.patchBible).mockResolvedValue({});
  });
  it("saves overlay patch", async () => {
    render(<BiblePage projectId="p1" />);
    await screen.findByDisplayValue("自动");
    fireEvent.change(screen.getByLabelText("logline"), { target: { value: "人工" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(api.patchBible).toHaveBeenCalledWith("p1", { logline: "人工" }));
  });
});
