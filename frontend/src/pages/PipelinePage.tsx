import { useEffect, useRef, useState } from "react";
import {
  cancelJob,
  getJob,
  getLatestJob,
  startJob,
  uploadSource,
  type Job,
} from "../api/client";

type Props = {
  projectId: string;
};

const ACTIVE = new Set(["queued", "running", "cancelling"]);
const TERMINAL = new Set(["succeeded", "failed", "step_failed", "cancelled"]);

function jobStorageKey(projectId: string) {
  return `aivp.activeJob.${projectId}`;
}

export function PipelinePage({ projectId }: Props) {
  const [file, setFile] = useState<File | null>(null);
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [uploading, setUploading] = useState(false);
  const [starting, setStarting] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [forceEnrich, setForceEnrich] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = () => {
    if (pollRef.current != null) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  };

  const rememberJob = (next: Job | null) => {
    setJob(next);
    if (next && ACTIVE.has(next.status)) {
      localStorage.setItem(jobStorageKey(projectId), next.id);
    } else {
      localStorage.removeItem(jobStorageKey(projectId));
    }
  };

  const pollJob = (jobId: string) => {
    stopPolling();
    pollRef.current = setInterval(() => {
      void (async () => {
        try {
          const j = await getJob(projectId, jobId);
          rememberJob(j);
          if (TERMINAL.has(j.status)) {
            stopPolling();
          }
          if (j.error_message && j.status !== "cancelled") {
            setError(j.error_message);
          }
        } catch (e) {
          setError(e instanceof Error ? e.message : String(e));
          stopPolling();
        }
      })();
    }, 1000);
  };

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      setError(null);
      try {
        const latest = await getLatestJob(projectId);
        if (cancelled) return;
        rememberJob(latest);
        if (ACTIVE.has(latest.status)) {
          pollJob(latest.id);
        }
      } catch {
        const cached = localStorage.getItem(jobStorageKey(projectId));
        if (!cached || cancelled) return;
        try {
          const j = await getJob(projectId, cached);
          if (cancelled) return;
          rememberJob(j);
          if (ACTIVE.has(j.status)) pollJob(j.id);
        } catch {
          localStorage.removeItem(jobStorageKey(projectId));
        }
      }
    })();
    return () => {
      cancelled = true;
      stopPolling();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

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

  const launchJob = async (options?: {
    forceEnrich?: boolean;
    forceShots?: boolean;
    resumeFromStep?: string;
  }) => {
    setStarting(true);
    setError(null);
    try {
      // Refresh latest job first so we can show / terminate a leftover active job.
      try {
        const latest = await getLatestJob(projectId);
        rememberJob(latest);
        if (ACTIVE.has(latest.status)) {
          setError(
            `已有进行中的任务 ${latest.id}（${latest.status}）。请先点击「终止」或「强制终止」，再重新启动。`,
          );
          if (ACTIVE.has(latest.status)) pollJob(latest.id);
          return;
        }
      } catch {
        // no jobs yet — ok to start
      }
      const j = await startJob(projectId, {
        forceEnrich: options?.forceEnrich,
        forceShots: options?.forceShots,
        resumeFromStep: options?.resumeFromStep,
      });
      rememberJob(j);
      if (j.error_message) setError(j.error_message);
      if (!TERMINAL.has(j.status)) {
        pollJob(j.id);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      try {
        const latest = await getLatestJob(projectId);
        rememberJob(latest);
      } catch {
        // ignore
      }
    } finally {
      setStarting(false);
    }
  };

  const onStart = async () => {
    await launchJob(forceEnrich ? { forceEnrich: true } : undefined);
  };

  const onForceEnrich = async () => {
    await launchJob({ forceEnrich: true, resumeFromStep: "06_enrich_assets" });
  };

  const onGenerateShots = async () => {
    await launchJob({ forceShots: true, resumeFromStep: "10_shot_script" });
  };

  const onCancel = async () => {
    if (!job) return;
    setCancelling(true);
    setError(null);
    try {
      const j = await cancelJob(projectId, job.id);
      rememberJob(j);
      if (!TERMINAL.has(j.status)) {
        pollJob(j.id);
      } else {
        stopPolling();
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCancelling(false);
    }
  };

  const pct =
    job && job.chunks_total > 0
      ? Math.min(100, Math.round((job.chunks_done / job.chunks_total) * 100))
      : 0;
  const active = Boolean(job && ACTIVE.has(job.status));

  return (
    <section className="panel">
      <h2>流水线</h2>
      <p className="panel-lead">上传小说 TXT，启动抽取任务，生成 Story Bible。</p>
      <p className="note">
        关闭或刷新前端<strong>不会</strong>停止后端任务；只有点击「终止」才会取消。
        进入 <code>04_extract</code> 后会逐块调用本地 Ollama，进度会缓慢上升（例如 1000+
        块可能需要数小时），并非卡死。
      </p>

      <div className="row">
        <input
          aria-label="source-file"
          type="file"
          accept=".txt,text/plain"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button
          type="button"
          className="btn btn-secondary"
          disabled={!file || uploading}
          onClick={() => void onUpload()}
        >
          {uploading ? "上传中…" : "上传原文"}
        </button>
      </div>

      <label className="row" style={{ alignItems: "center", gap: 8 }}>
        <input
          type="checkbox"
          aria-label="force-enrich"
          checked={forceEnrich}
          onChange={(e) => setForceEnrich(e.target.checked)}
          disabled={starting || active}
        />
        <span>启动时强制重 enrich（忽略已有资产卡）</span>
      </label>

      <div className="row">
        <button
          type="button"
          className="btn btn-primary"
          disabled={starting || active}
          onClick={() => void onStart()}
        >
          {starting ? "启动中…" : "启动任务"}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={starting || active}
          onClick={() => void onForceEnrich()}
        >
          从 Enrich 重跑
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={starting || active}
          onClick={() => void onGenerateShots()}
        >
          生成分镜
        </button>
        <button
          type="button"
          className="btn btn-danger"
          disabled={!job || !active || cancelling}
          onClick={() => void onCancel()}
        >
          {cancelling
            ? "终止中…"
            : job?.status === "cancelling"
              ? "强制终止"
              : "终止"}
        </button>
      </div>

      {job && (
        <div className="status-card">
          <div className="row" style={{ marginBottom: 0 }}>
            <span className={`status-pill is-${job.status}`}>{job.status}</span>
            <span>步骤 {job.current_step ?? "—"}</span>
            <span style={{ color: "var(--ink-soft)" }}>job {job.id}</span>
          </div>
          <div>
            Chunk 进度：{job.chunks_done}/{job.chunks_total}
            {(job.volumes_total ?? 0) > 0
              ? ` · 卷 ${job.volumes_done ?? 0}/${job.volumes_total}`
              : ""}
          </div>
          <div className="progress-track" aria-hidden>
            <div className="progress-fill" style={{ width: `${pct}%` }} />
          </div>
          {job.error_message && job.status !== "cancelled" && (
            <p className="alert" role="alert">
              错误：{job.error_message}
            </p>
          )}
          {job.status === "cancelled" && (
            <p className="note">任务已被终止。可从失败/中断步骤重新启动（若支持续跑）。</p>
          )}
        </div>
      )}

      {error && !job?.error_message && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
    </section>
  );
}
