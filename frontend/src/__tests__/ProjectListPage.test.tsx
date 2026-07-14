import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ProjectListPage } from "../pages/ProjectListPage";
import * as api from "../api/client";

vi.mock("../api/client");

describe("ProjectListPage", () => {
  beforeEach(() => {
    vi.mocked(api.listProjects).mockResolvedValue([]);
    vi.mocked(api.createProject).mockResolvedValue({ id: "p1", name: "仙侠" });
  });

  it("shows validation error when creating with empty name", async () => {
    render(<ProjectListPage onSelect={vi.fn()} />);
    await screen.findByText("暂无项目");
    fireEvent.click(screen.getByRole("button", { name: "新建项目" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("请先输入项目名称");
    expect(api.createProject).not.toHaveBeenCalled();
  });

  it("creates project and selects it", async () => {
    const onSelect = vi.fn();
    render(<ProjectListPage onSelect={onSelect} />);
    await screen.findByText("暂无项目");
    fireEvent.change(screen.getByLabelText("project-name"), {
      target: { value: "仙侠" },
    });
    fireEvent.click(screen.getByRole("button", { name: "新建项目" }));
    await waitFor(() => expect(api.createProject).toHaveBeenCalledWith("仙侠"));
    await waitFor(() => expect(onSelect).toHaveBeenCalledWith("p1"));
  });
});
