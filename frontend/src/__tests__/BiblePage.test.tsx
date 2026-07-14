import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BiblePage } from "../pages/BiblePage";
import * as api from "../api/client";

vi.mock("../api/client");

describe("BiblePage", () => {
  beforeEach(() => {
    vi.mocked(api.getBible).mockResolvedValue({
      logline: "自动",
      project_meta: { title: "T" },
      characters: [
        {
          name: "林砚之",
          tier: "major",
          prompt_zh: "清俊少年青灰长衫",
          appearance: { face: "清俊", hair: "束发" },
          wardrobe: { default: "青灰长衫" },
          voice: { timbre: "清柔" },
        },
      ],
    });
    vi.mocked(api.patchBible).mockResolvedValue({});
  });

  it("saves overlay patch", async () => {
    render(<BiblePage projectId="p1" />);
    await screen.findByDisplayValue("自动");
    fireEvent.change(screen.getByLabelText("logline"), { target: { value: "人工" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(api.patchBible).toHaveBeenCalledWith("p1", { logline: "人工" }));
  });

  it("renders readable character cards", async () => {
    render(<BiblePage projectId="p1" />);
    await screen.findByDisplayValue("自动");
    fireEvent.click(screen.getByRole("button", { name: "5. 主要角色 Bible" }));
    expect(await screen.findByText("林砚之")).toBeInTheDocument();
    expect(screen.getByText(/清俊少年青灰长衫/)).toBeInTheDocument();
    expect(screen.getByLabelText("characters-cards")).toBeInTheDocument();
  });
});
