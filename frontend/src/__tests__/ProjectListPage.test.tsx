import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { ProjectListPage } from "../pages/ProjectListPage";
import * as api from "../api/client";

vi.mock("../api/client");

describe("ProjectListPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(api.listProjects).mockResolvedValue([
      { id: "p1", name: "仙侠", created_at: null, export_version: 0 },
    ]);
    vi.mocked(api.createProject).mockResolvedValue({ id: "p1", name: "仙侠" });
    vi.mocked(api.deleteProject).mockResolvedValue({ deleted: true, id: "p1" });
    vi.spyOn(window, "confirm").mockReturnValue(true);
  });

  it("shows validation error when creating with empty name", async () => {
    vi.mocked(api.listProjects).mockResolvedValueOnce([]);
    render(<ProjectListPage onSelect={vi.fn()} />);
    await screen.findByText("暂无项目");
    fireEvent.click(screen.getByRole("button", { name: "新建项目" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("请先输入项目名称");
    expect(api.createProject).not.toHaveBeenCalled();
  });

  it("creates project and selects it", async () => {
    vi.mocked(api.listProjects).mockResolvedValueOnce([]);
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

  it("deletes project after confirm", async () => {
    const onDeleted = vi.fn();
    render(<ProjectListPage onSelect={vi.fn()} onDeleted={onDeleted} />);
    await screen.findByText("仙侠");
    fireEvent.click(screen.getByRole("button", { name: "删除项目 仙侠" }));
    await waitFor(() => expect(api.deleteProject).toHaveBeenCalledWith("p1"));
    await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("p1"));
  });

  it("does not delete when confirm cancelled", async () => {
    vi.mocked(window.confirm).mockReturnValue(false);
    render(<ProjectListPage onSelect={vi.fn()} />);
    await screen.findByText("仙侠");
    fireEvent.click(screen.getByRole("button", { name: "删除项目 仙侠" }));
    expect(api.deleteProject).not.toHaveBeenCalled();
  });
});
