import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { PipelinePage } from "../pages/PipelinePage";
import * as api from "../api/client";

vi.mock("../api/client");

describe("PipelinePage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    localStorage.clear();
    vi.mocked(api.getLatestJob).mockRejectedValue(new Error("no jobs"));
    vi.mocked(api.listPipelineReports).mockResolvedValue({ reports: [] });
    vi.mocked(api.getPipelineReport).mockResolvedValue({ chapter_count: 2 });
    vi.mocked(api.startJob).mockResolvedValue({
      id: "j1",
      project_id: "p1",
      status: "running",
      current_step: "04_extract",
      chunks_done: 2,
      chunks_total: 10,
    });
    vi.mocked(api.getJob).mockResolvedValue({
      id: "j1",
      project_id: "p1",
      status: "running",
      current_step: "04_extract",
      chunks_done: 3,
      chunks_total: 10,
    });
    vi.mocked(api.uploadSource).mockResolvedValue({
      ok: true,
      path: "raw/source.txt",
      bytes: 12,
    });
    vi.mocked(api.cancelJob).mockResolvedValue({
      id: "j1",
      project_id: "p1",
      status: "cancelling",
      current_step: "04_extract",
      chunks_done: 3,
      chunks_total: 10,
    });
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("starts job and shows progress", async () => {
    render(<PipelinePage projectId="p1" />);

    fireEvent.click(screen.getByRole("button", { name: /启动任务/ }));

    await waitFor(() => {
      expect(api.startJob).toHaveBeenCalledWith("p1", {
        forceEnrich: undefined,
        forceShots: undefined,
        resumeFromStep: undefined,
      });
    });

    await waitFor(() => {
      expect(screen.getByText(/步骤\s*04_extract/)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/Chunk 进度：\s*3\/10/)).toBeInTheDocument();
    });
  });

  it("stops polling when getJob returns step_failed", async () => {
    vi.mocked(api.getJob).mockResolvedValue({
      id: "j1",
      project_id: "p1",
      status: "step_failed",
      current_step: "04_extract",
      chunks_done: 3,
      chunks_total: 10,
      error_message: "extract failed",
    });

    render(<PipelinePage projectId="p1" />);
    fireEvent.click(screen.getByRole("button", { name: /启动任务/ }));

    await waitFor(() => {
      expect(api.startJob).toHaveBeenCalledWith("p1", {
        forceEnrich: undefined,
        forceShots: undefined,
        resumeFromStep: undefined,
      });
    });

    await vi.advanceTimersByTimeAsync(1000);

    await waitFor(() => {
      expect(screen.getByText(/step_failed/)).toBeInTheDocument();
    });

    const callsAfterTerminal = vi.mocked(api.getJob).mock.calls.length;
    expect(callsAfterTerminal).toBeGreaterThan(0);

    await vi.advanceTimersByTimeAsync(3000);
    expect(vi.mocked(api.getJob).mock.calls.length).toBe(callsAfterTerminal);
  });

  it("cancels active job via terminate button", async () => {
    render(<PipelinePage projectId="p1" />);
    fireEvent.click(screen.getByRole("button", { name: /启动任务/ }));

    await waitFor(() => {
      expect(screen.getByRole("button", { name: "终止" })).not.toBeDisabled();
    });

    fireEvent.click(screen.getByRole("button", { name: "终止" }));

    await waitFor(() => {
      expect(api.cancelJob).toHaveBeenCalledWith("p1", "j1");
    });
  });

  it("shows text quality reports and opens preview", async () => {
    vi.mocked(api.listPipelineReports).mockResolvedValue({
      reports: [
        { name: "chapters", available: true, path: "stages/02_chapters/chapter_report.json" },
        { name: "extract", available: false, path: "stages/04_extract/extract_report.json" },
      ],
    });
    vi.mocked(api.getPipelineReport).mockResolvedValue({
      chapter_count: 3,
      maybe_unsplit: false,
    });

    render(<PipelinePage projectId="p1" />);

    expect(await screen.findByText("文本质量报告")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "刷新报告" }));

    await waitFor(() => {
      expect(api.listPipelineReports).toHaveBeenCalledWith("p1");
    });

    const chapterBtn = await screen.findByRole("button", { name: "章节" });
    expect(chapterBtn).not.toBeDisabled();
    expect(screen.getByRole("button", { name: "抽取（无）" })).toBeDisabled();

    fireEvent.click(chapterBtn);
    await waitFor(() => {
      expect(api.getPipelineReport).toHaveBeenCalledWith("p1", "chapters");
    });
    expect(await screen.findByText(/"chapter_count": 3/)).toBeInTheDocument();
  });
});
