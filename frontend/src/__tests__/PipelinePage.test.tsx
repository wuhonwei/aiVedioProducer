import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { PipelinePage } from "../pages/PipelinePage";
import * as api from "../api/client";

vi.mock("../api/client");

describe("PipelinePage", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
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
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.clearAllMocks();
  });

  it("starts job and shows progress", async () => {
    render(<PipelinePage projectId="p1" />);

    fireEvent.click(screen.getByRole("button", { name: /启动|开始/ }));

    await waitFor(() => {
      expect(api.startJob).toHaveBeenCalledWith("p1", undefined);
    });

    await waitFor(() => {
      expect(screen.getByText(/04_extract/)).toBeInTheDocument();
    });

    await waitFor(() => {
      expect(screen.getByText(/3\s*\/\s*10|3\/10/)).toBeInTheDocument();
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
    fireEvent.click(screen.getByRole("button", { name: /启动|开始/ }));

    await waitFor(() => {
      expect(api.startJob).toHaveBeenCalledWith("p1", undefined);
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
});
