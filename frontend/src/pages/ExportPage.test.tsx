import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ExportPage } from "./ExportPage";
import * as client from "../api/client";

describe("ExportPage", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("calls createExport and shows download links with API URLs", async () => {
    const createExport = vi.spyOn(client, "createExport").mockResolvedValue({
      version: 1,
      json_url: "/api/projects/p1/exports/1/json",
      md_url: "/api/projects/p1/exports/1/md",
    });
    const user = userEvent.setup();

    render(<ExportPage projectId="p1" />);
    await user.click(screen.getByRole("button", { name: "创建导出" }));

    await waitFor(() => {
      expect(createExport).toHaveBeenCalledWith("p1");
    });

    const jsonLink = screen.getByRole("link", { name: "下载 JSON" });
    const mdLink = screen.getByRole("link", { name: "下载 Markdown" });
    expect(jsonLink).toHaveAttribute("href", "/api/projects/p1/exports/1/json");
    expect(mdLink).toHaveAttribute("href", "/api/projects/p1/exports/1/md");
    expect(jsonLink.getAttribute("href")).toContain("/api/projects/");
    expect(mdLink.getAttribute("href")).toContain("/api/projects/");
    expect(jsonLink.getAttribute("href")).toContain("/exports/");
  });
});
