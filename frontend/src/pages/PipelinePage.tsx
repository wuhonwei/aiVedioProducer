import { useEffect, useRef, useState } from "react";
import {
  getJob,
  startJob,
  uploadSource,
  type Job,
} from "../api/client";

type Props = {
  projectId: string;
};

export function PipelinePage({ projectId }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current != null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  useEffect(() => () => stopPolling(), []);

  const pollJob = (jobId: string) => {
    stopPolling();
    pollRef.current = setInterval(() => {
      void (async () => {
        try {
          const j = await getJob(projectId, jobId);
          setJob(j);
          if (j.status === "succeeded" || j.status === "failed") {
            stopPolling();
          }
          if (j.error_message) {
            setError(j.error_message);
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
          stopPolling();
        }
      })();
    }, 1000);
  };

  const onUpload = async () => {
    if (!file) return;
    setUploading(true);
    setError(null);
    try {
      await uploadSource(projectId, file);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setUploading(false);
    }
  };

  const onStart = async () => {
    setStarting(true);
    setError(null);
    try {
      const j = await startJob(projectId, undefined);
      setJob(j);
      if (j.error_message) setError(j.error_message);
      if (j.status !== "succeeded" && j.status !== "failed") {
        pollJob(j.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setStarting(false);
    }
  };

  return (
    <section>
      <h2>流水线</h2>
      <p>项目：{projectId}</p>

      <div style={{ marginBottom: 12 }}>
        <input
          aria-label="source-file"
          type="file"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button type="button" disabled={!file || uploading} onClick={() => void onUpload()}>
          {uploading ? "上传中…" : "上传原文"}
        </button>
      </div>

      <div style={{ marginBottom: 12 }}>
        <button type="button" disabled={starting} onClick={() => void onStart()}>
          {starting ? "启动中…" : "启动任务"}
        </button>
      </div>

      {job && (
        <div>
          <p>
            状态：{job.status} / 当前步骤：
            <span>{job.current_step ?? "—"}</span>
          </p>
          <p>
            Chunk 进度：{job.chunks_done}/{job.chunks_total}
          </p>
          {job.error_message && (
            <p role="alert">错误：{job.error_message}</p>
          )}
        </div>
      )}

      {error && !job?.error_message && <p role="alert">{error}</p>}
    </section>
  );
}
