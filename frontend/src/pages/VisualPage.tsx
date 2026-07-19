import { useEffect, useState, type ReactNode } from "react";
import {
  approveVisualLora,
  checkVisualTrainset,
  clearVisualLookLock,
  confirmVisualBootstrap,
  confirmVisualLocationBootstrap,
  curateVisualCharacter,
  deleteVisualFile,
  getVisualJob,
  listVisualCharacters,
  listVisualLocations,
  packageVisualLora,
  packageVisualLoraBatch,
  probeVisualLora,
  rejectVisualLora,
  setVisualLookLock,
  skipVisualBootstrap,
  skipVisualLocationBootstrap,
  startVisualBootstrap,
  startVisualLocationBootstrap,
  startVisualCandidates,
  startVisualLoraTrain,
  startVisualLoraTrainBatch,
  startVisualSheets,
  swapVisualBootstrapLookLock,
  swapVisualLocationBootstrapLookLock,
  rebuildExpressionDims,
  visualFileUrl,
  visualLocationFileUrl,
  type VisualCharacter,
  type VisualLocation,
} from "../api/client";

type Props = { projectId: string };

/** Optional probe extra only — backend builds the training-aligned prompt when empty. */
export function defaultProbePrompt(_c: Pick<VisualCharacter, "name" | "prompt_zh">): string {
  return "";
}

type Lightbox = { src: string; title: string } | null;

function sheetLabel(filename: string): string {
  const map: Record<string, string> = {
    sheet_turnaround_front: "三视图·正面",
    sheet_turnaround_side: "三视图·侧面",
    sheet_turnaround_back: "三视图·背面",
    sheet_expr_calm: "平静",
    sheet_expr_smile: "微笑",
    sheet_expr_happy: "开心",
    sheet_expr_confused: "疑惑",
    sheet_expr_angry: "愤怒",
    sheet_expr_sad: "悲伤",
    sheet_expr_surprised: "惊讶",
    sheet_expr_shy: "害羞",
  };
  const base = filename.replace(/\.png$/i, "");
  // Prefer longest key match so sheet_expr_calm_TIMESTAMP still labels as 平静
  const keys = Object.keys(map).sort((a, b) => b.length - a.length);
  for (const key of keys) {
    if (base === key || base.startsWith(`${key}_`)) return map[key];
  }
  return filename;
}

export function VisualPage({ projectId }: Props) {
  const [visualTab, setVisualTab] = useState<"characters" | "locations">("characters");
  const [chars, setChars] = useState<VisualCharacter[]>([]);
  const [locations, setLocations] = useState<VisualLocation[]>([]);
  const [backend, setBackend] = useState("stub");
  const [loraTrainConfigured, setLoraTrainConfigured] = useState(false);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [activeLocationId, setActiveLocationId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [selectedSheets, setSelectedSheets] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [probePrompt, setProbePrompt] = useState("");
  const [probeResult, setProbeResult] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<Lightbox>(null);
  const [batchCount, setBatchCount] = useState(8);
  const [lookLockDenoise, setLookLockDenoise] = useState(0.55);
  const [jobProgress, setJobProgress] = useState<{
    done: number;
    total: number;
    note?: string | null;
    kind?: string | null;
    characterId?: string | null;
    step?: string | null;
    items?: Array<{
      character_id: string;
      name: string;
      status: string;
      error?: string | null;
      lora_file?: string | null;
    }>;
    skipped?: Array<{
      character_id: string;
      name: string;
      status: string;
      error?: string | null;
      lora_file?: string | null;
    }>;
  } | null>(null);
  const [trainCheck, setTrainCheck] = useState<{
    can_train: boolean;
    score: number;
    image_count: number;
    caption_count: number;
    turnaround_count: number;
    expression_count: number;
    candidate_count: number;
    has_front: boolean;
    has_side: boolean;
    has_back: boolean;
    warnings: string[];
  } | null>(null);

  const refresh = async () => {
    const data = await listVisualCharacters(projectId);
    setChars(data.characters);
    setBackend(data.backend);
    setLoraTrainConfigured(Boolean(data.lora_train_configured));
    if (!activeId && data.characters[0]) {
      setActiveId(data.characters[0].character_id);
    }
    try {
      const locData = await listVisualLocations(projectId);
      setLocations(locData.locations);
      if (!activeLocationId && locData.locations[0]) {
        setActiveLocationId(locData.locations[0].location_id);
      }
    } catch {
      /* bible may lack locations yet */
      setLocations([]);
    }
  };

  useEffect(() => {
    void (async () => {
      try {
        await refresh();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId]);

  const active = chars.find((c) => c.character_id === activeId) || null;
  const activeLocation =
    locations.find((l) => l.location_id === activeLocationId) || null;

  useEffect(() => {
    if (!active) return;
    setSelected((prev) => {
      const next: Record<string, boolean> = {};
      for (const name of active.candidates) {
        next[name] =
          name in prev ? Boolean(prev[name]) : active.curated.includes(name);
      }
      return next;
    });
    setSelectedSheets((prev) => {
      const sheets = active.sheets || [];
      const hasCuratedSheets = sheets.some((n) => active.curated.includes(n));
      const next: Record<string, boolean> = {};
      for (const name of sheets) {
        if (name in prev) {
          next[name] = Boolean(prev[name]);
        } else {
          next[name] = hasCuratedSheets
            ? active.curated.includes(name)
            : true;
        }
      }
      return next;
    });
  }, [active?.character_id, active?.candidates, active?.sheets, active?.curated]);

  useEffect(() => {
    if (!active) return;
    setProbePrompt(defaultProbePrompt(active));
    setProbeResult(null);
    setTrainCheck(null);
  }, [active?.character_id, active?.prompt_zh, active?.name]);

  const pollJob = async (jobId: string) => {
    let lastDone = -1;
    let lastStatus = "";
    let lastNote = "";
    let kind = "";
    // Image jobs ~10min; LoRA train can take hours.
    for (let i = 0; i < 20000; i++) {
      const j = await getVisualJob(projectId, jobId);
      kind = String(j.kind || kind || "");
      const isTrain =
        kind === "lora_train" || kind === "lora_train_batch";
      const isBootstrap =
        kind === "visual_bootstrap" || kind === "visual_location_bootstrap";
      const done = Number(j.progress_done || 0);
      const total = Number(j.progress_total || 0);
      const note = typeof j.progress_note === "string" ? j.progress_note : null;
      const status = String(j.status || "");
      const defaultNote = isTrain
        ? status === "running"
          ? kind === "lora_train_batch"
            ? `批量微调进行中 ${done}/${Math.max(total, 1)}…`
            : "LoRA 微调进行中…（通常需数十分钟，请勿关闭页面）"
          : status === "succeeded"
            ? kind === "lora_train_batch"
              ? "批量微调完成"
              : "微调完成"
            : `微调 ${done}/${Math.max(total, 1)}`
        : isBootstrap
          ? note ||
            (total > 0
              ? `初始化训练集 ${done}/${total}${j.bootstrap_step ? ` · ${j.bootstrap_step}` : ""}`
              : kind === "visual_location_bootstrap"
                ? "初始化地点训练集…"
                : "初始化视觉训练集…")
          : total > 0
            ? done < total
              ? `正在生成第 ${done + 1}/${total} 张（已完成 ${done}）`
              : `已完成 ${done}/${total}`
            : null;
      if (total > 0 || note || isTrain || isBootstrap) {
        setJobProgress({
          done,
          total: Math.max(total, 1),
          note: note || defaultNote,
          kind,
          characterId: j.current_character_id || j.current_location_id || null,
          step: j.bootstrap_step || null,
          items: Array.isArray(j.items) ? j.items : undefined,
          skipped: Array.isArray(j.skipped) ? j.skipped : undefined,
        });
      }
      // Refresh gallery whenever progress advances or status/note changes.
      if (
        (done !== lastDone || status !== lastStatus || (note || "") !== lastNote) &&
        (status === "running" || status === "succeeded" || status === "failed")
      ) {
        lastDone = done;
        lastStatus = status;
        lastNote = note || "";
        try {
          await refresh();
        } catch {
          /* keep polling even if refresh fails once */
        }
      }
      if (status === "succeeded" || status === "failed") return j;
      await new Promise((r) => setTimeout(r, isTrain ? 1500 : 500));
    }
    throw new Error("visual job timeout");
  };

  const runVisualJob = async (start: () => Promise<{ id: string }>) => {
    setBusy(true);
    setError(null);
    setJobProgress(null);
    let keepProgress = false;
    try {
      const job = await start();
      const done = await pollJob(job.id);
      const kind = String(done.kind || "");
      // Keep batch train panel so users can compare per-character results.
      // Keep bootstrap progress briefly so confirm UI can follow refresh.
      keepProgress =
        kind === "lora_train_batch" ||
        kind === "visual_bootstrap" ||
        kind === "visual_location_bootstrap";
      if (done.status === "failed") throw new Error(done.error || "visual job failed");
      if (done.error && String(done.error).startsWith("partial_failed:")) {
        setError(`批量微调部分失败：${done.error}`);
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
      if (!keepProgress) setJobProgress(null);
    }
  };

  const onBootstrap = () =>
    void runVisualJob(() =>
      startVisualBootstrap(projectId, {
        character_ids: activeId ? [activeId] : undefined,
      }),
    );

  const onBootstrapAll = () =>
    void runVisualJob(() => startVisualBootstrap(projectId, {}));

  const onLocationBootstrap = () =>
    void runVisualJob(() =>
      startVisualLocationBootstrap(projectId, {
        location_ids: activeLocationId ? [activeLocationId] : undefined,
      }),
    );

  const onLocationBootstrapAll = () =>
    void runVisualJob(() => startVisualLocationBootstrap(projectId, {}));

  const onConfirmLocationBootstrap = async () => {
    if (!activeLocation) return;
    setBusy(true);
    setError(null);
    try {
      await confirmVisualLocationBootstrap(projectId, activeLocation.location_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onSkipLocationBootstrap = async () => {
    if (!activeLocation) return;
    setBusy(true);
    setError(null);
    try {
      await skipVisualLocationBootstrap(projectId, activeLocation.location_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onSwapLocationBootstrapLock = async (filename: string) => {
    if (!activeLocation) return;
    setBusy(true);
    setError(null);
    try {
      await swapVisualLocationBootstrapLookLock(
        projectId,
        activeLocation.location_id,
        { filename, folder: "look_lock_archive" },
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onConfirmBootstrap = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await confirmVisualBootstrap(projectId, active.character_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onSkipBootstrap = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await skipVisualBootstrap(projectId, active.character_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onSwapBootstrapLock = async (filename: string) => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await swapVisualBootstrapLookLock(projectId, active.character_id, {
        filename,
        folder: "look_lock_archive",
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onCandidatesOnce = () =>
    void runVisualJob(() =>
      startVisualCandidates(projectId, {
        character_ids: activeId ? [activeId] : undefined,
        count: 1,
      }),
    );

  const onCandidatesBatch = () => {
    const n = Math.max(1, Math.min(100, Math.floor(Number(batchCount) || 8)));
    void runVisualJob(() =>
      startVisualCandidates(projectId, {
        character_ids: activeId ? [activeId] : undefined,
        count: n,
      }),
    );
  };

  const onTurnaroundOnce = (slotKey: string) => {
    if (!active) return;
    void runVisualJob(() =>
      startVisualSheets(projectId, active.character_id, { slot_keys: [slotKey] }),
    );
  };

  const onTurnaroundBatch = () => {
    if (!active) return;
    void runVisualJob(() =>
      startVisualSheets(projectId, active.character_id, { group: "turnaround" }),
    );
  };

  const onExpressionOnce = (slotKey: string) => {
    if (!active) return;
    void runVisualJob(() =>
      startVisualSheets(projectId, active.character_id, { slot_keys: [slotKey] }),
    );
  };

  const expressionButtons = (() => {
    const dims = (active?.expression_dims || []).filter(
      (d) => d.status !== "rejected" && d.status !== "stale",
    );
    if (dims.length) {
      return dims.map((d) => [d.id, d.label || d.id] as [string, string]);
    }
    return [
      ["expr_calm", "平静"],
      ["expr_smile", "微笑"],
      ["expr_happy", "开心"],
      ["expr_confused", "疑惑"],
      ["expr_angry", "愤怒"],
      ["expr_sad", "悲伤"],
      ["expr_surprised", "惊讶"],
      ["expr_shy", "害羞"],
    ] as [string, string][];
  })();

  const onRebuildExpressionDims = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await rebuildExpressionDims(projectId, active.character_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onExpressionBatch = () => {
    if (!active) return;
    void runVisualJob(() =>
      startVisualSheets(projectId, active.character_id, { group: "expression" }),
    );
  };

  const onSheetsAll = () => {
    if (!active) return;
    void runVisualJob(() =>
      startVisualSheets(projectId, active.character_id, { group: "all" }),
    );
  };

  const onCurate = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      const keep = Object.entries(selected)
        .filter(([, v]) => v)
        .map(([k]) => k);
      const keepSheets = Object.entries(selectedSheets)
        .filter(([, v]) => v)
        .map(([k]) => k);
      if (!keep.length && !keepSheets.length) {
        throw new Error("请至少勾选候选图或角色表（三视图/表情）加入训练集");
      }
      await curateVisualCharacter(projectId, active.character_id, keep, keepSheets);
      const check = await checkVisualTrainset(projectId, active.character_id);
      setTrainCheck(check);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const selectAllSheetsForLora = () => {
    if (!active?.sheets?.length) return;
    const next: Record<string, boolean> = {};
    for (const name of active.sheets) next[name] = true;
    setSelectedSheets(next);
  };

  const onCheckTrainset = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      setTrainCheck(await checkVisualTrainset(projectId, active.character_id));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onPackage = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await packageVisualLora(projectId, active.character_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onPackageBatch = async () => {
    setBusy(true);
    setError(null);
    try {
      const out = await packageVisualLoraBatch(projectId);
      const ok = (out.results || []).filter((r) => r.packaged !== false).length;
      const fail = (out.results || []).length - ok;
      if (fail > 0) {
        setError(`批量导出完成：成功 ${ok}，跳过/失败 ${fail}（需先确认可训练训练集）`);
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onTrain = async () => {
    if (!active) return;
    if (!loraTrainConfigured) {
      setError(
        "尚未配置 AIVP_LORA_TRAIN_CMD，无法真正开始微调。请在 backend/.env 设置 kohya/sd-scripts 训练命令后再试。",
      );
      return;
    }
    await runVisualJob(() => startVisualLoraTrain(projectId, active.character_id));
  };

  const onTrainBatch = async () => {
    if (!loraTrainConfigured) {
      setError(
        "尚未配置 AIVP_LORA_TRAIN_CMD，无法批量微调。请先配置训练命令。",
      );
      return;
    }
    await runVisualJob(() =>
      startVisualLoraTrainBatch(projectId, {
        auto_package: true,
      }),
    );
  };

  const onProbe = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      const r = await probeVisualLora(projectId, active.character_id, probePrompt);
      const file = String(r.file || "");
      const usedPrompt = String(r.prompt || "");
      if (usedPrompt) setProbePrompt(usedPrompt);
      setProbeResult(
        file
          ? visualFileUrl(projectId, active.character_id, "generations", file)
          : null,
      );
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onApproveLora = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await approveVisualLora(projectId, active.character_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onRejectLora = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await rejectVisualLora(projectId, active.character_id, "probe_rejected");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onDelete = async (folder: string, filename: string) => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await deleteVisualFile(projectId, active.character_id, folder, filename);
      if (probeResult?.includes(`/generations/${filename}`)) {
        setProbeResult(null);
      }
      setLightbox(null);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onSetLookLock = async (
    folder: string,
    filename: string,
    denoise = lookLockDenoise,
  ) => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      setLookLockDenoise(denoise);
      await setVisualLookLock(projectId, active.character_id, {
        folder,
        filename,
        denoise,
      });
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onClearLookLock = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await clearVisualLookLock(projectId, active.character_id);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const isLookLockSource = (folder: string, name: string) =>
    Boolean(
      active?.look_lock &&
        active.look_lock.folder === folder &&
        active.look_lock.file === name,
    );

  const renderThumb = (
    folder: "candidates" | "sheets" | "generations",
    name: string,
    title: string,
    extra?: ReactNode,
  ) => {
    if (!active) return null;
    const src = visualFileUrl(projectId, active.character_id, folder, name);
    const locked = isLookLockSource(folder, name);
    return (
      <div key={`${folder}-${name}`} className="bible-card" style={{ position: "relative" }}>
        <div className="row" style={{ marginBottom: 8, justifyContent: "space-between" }}>
          <span>
            {title}
            {locked ? " · 定妆" : ""}
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => void onDelete(folder, name)}
            aria-label={`删除 ${title}`}
          >
            删除
          </button>
        </div>
        {extra}
        <div className="row" style={{ marginBottom: 8 }}>
          <button
            type="button"
            className={locked ? "btn btn-primary" : "btn btn-secondary"}
            disabled={busy}
            onClick={() => void onSetLookLock(folder, name)}
          >
            {locked ? "当前定妆" : "设为定妆"}
          </button>
        </div>
        <button
          type="button"
          onClick={() => setLightbox({ src, title })}
          style={{
            display: "block",
            width: "100%",
            padding: 0,
            border: locked ? "2px solid var(--accent)" : "none",
            background: "transparent",
            cursor: "zoom-in",
            borderRadius: 8,
          }}
          aria-label={`放大 ${title}`}
        >
          <img
            src={src}
            alt={title}
            className="visual-thumb-img"
          />
        </button>
      </div>
    );
  };

  return (
    <section className="panel">
      <h2>视觉 / LoRA</h2>
      <p className="panel-lead">
        major 角色与地点：自动定妆 / 空镜训练集 → 人工确认 → 训练。当前后端：
        <strong> {backend}</strong>
        {backend === "stub" ? "（占位出图，接好 Comfy 后改 AIVP_IMAGE_BACKEND=comfy）" : ""}。
      </p>
      <div className="row" style={{ flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
        <button
          type="button"
          className={visualTab === "characters" ? "btn btn-primary" : "btn btn-secondary"}
          disabled={busy}
          onClick={() => setVisualTab("characters")}
        >
          角色
        </button>
        <button
          type="button"
          className={visualTab === "locations" ? "btn btn-primary" : "btn btn-secondary"}
          disabled={busy}
          onClick={() => setVisualTab("locations")}
        >
          地点
        </button>
      </div>

      {visualTab === "locations" ? (
        <>
          <div className="row" style={{ flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy}
              onClick={onLocationBootstrap}
            >
              初始化地点训练集
              {activeLocation ? `（${activeLocation.name}）` : ""}
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={onLocationBootstrapAll}
            >
              全部 major 地点初始化
            </button>
            <span className="note" style={{ margin: 0 }}>
              空镜定妆 + 多角度/时段扩展；确认前不自动训 LoRA
            </span>
          </div>
          {jobProgress && (
            <div className="bible-card" aria-label="job-progress" style={{ marginBottom: 12 }}>
              <p className="note" role="status" style={{ marginBottom: 0 }}>
                {jobProgress.note ||
                  `进度 ${jobProgress.done}/${jobProgress.total}`}
                {jobProgress.step ? ` · ${jobProgress.step}` : ""}
              </p>
            </div>
          )}
          <div className="bible-layout visual-layout">
            <nav className="visual-char-nav" aria-label="visual-locations">
              <ul>
                {locations.map((l) => {
                  const isActive = l.location_id === activeLocationId;
                  return (
                    <li key={l.location_id}>
                      <button
                        type="button"
                        className="visual-char-item"
                        aria-current={isActive ? "page" : undefined}
                        onClick={() => setActiveLocationId(l.location_id)}
                      >
                        <span className="visual-char-name">{l.name}</span>
                        <span className="visual-char-stats">
                          候选 {l.candidate_count} · 表 {l.sheet_count ?? 0} · 已选{" "}
                          {l.curated_count}
                        </span>
                        <span className="visual-char-flags">
                          {l.bootstrap_status === "awaiting_confirm" ? (
                            <span className="visual-char-flag">待确认</span>
                          ) : null}
                          {l.lora_ready ? (
                            <span className="visual-char-flag is-ok">LoRA</span>
                          ) : null}
                        </span>
                      </button>
                    </li>
                  );
                })}
              </ul>
            </nav>
            <div className="stack">
              {!activeLocation && (
                <p className="note">暂无 major 地点，请先跑通 Story Bible。</p>
              )}
              {activeLocation && (
                <>
                  <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>
                    {activeLocation.name}
                  </h3>
                  <p className="note">
                    trigger：<code>{activeLocation.trigger}</code> · train{" "}
                    {activeLocation.train_status || "not_started"}
                    {activeLocation.bootstrap_status &&
                    activeLocation.bootstrap_status !== "not_started"
                      ? ` · bootstrap ${activeLocation.bootstrap_status}`
                      : ""}
                  </p>
                  <p className="bible-plain">
                    {activeLocation.prompt_zh || "（无 prompt_zh）"}
                  </p>
                  {activeLocation.look_lock_ready && (
                    <div className="visual-thumb" style={{ maxWidth: 280 }}>
                      <img
                        src={visualLocationFileUrl(
                          projectId,
                          activeLocation.location_id,
                          "look_lock",
                          "ref.png",
                        )}
                        alt="地点定妆"
                        className="visual-thumb-img"
                      />
                      <span className="visual-char-stats">建立镜头定妆</span>
                    </div>
                  )}
                  {(activeLocation.bootstrap_status === "awaiting_confirm" ||
                    activeLocation.bootstrap_status === "look_lock_needs_review" ||
                    activeLocation.bootstrap_status ===
                      "description_needs_review") && (
                    <div className="bible-card" aria-label="location-bootstrap-review">
                      <h4 style={{ marginTop: 0 }}>地点训练集待确认</h4>
                      {!!(activeLocation.bootstrap_warnings || []).length && (
                        <ul className="note">
                          {(activeLocation.bootstrap_warnings || [])
                            .slice(0, 8)
                            .map((w) => (
                              <li key={w}>{w}</li>
                            ))}
                        </ul>
                      )}
                      {!!(activeLocation.look_lock_archive || []).length && (
                        <>
                          <p className="note">备选定妆（点选替换）：</p>
                          <div
                            className="bible-cards visual-thumbs"
                            aria-label="location-lock-archive"
                          >
                            {(activeLocation.look_lock_archive || []).map((name) => (
                              <div key={name} className="visual-thumb">
                                <button
                                  type="button"
                                  disabled={busy}
                                  onClick={() => void onSwapLocationBootstrapLock(name)}
                                  style={{
                                    display: "block",
                                    width: "100%",
                                    padding: 0,
                                    border: "1px solid var(--border)",
                                    background: "transparent",
                                    cursor: "pointer",
                                    borderRadius: 8,
                                  }}
                                  aria-label={`换定妆 ${name}`}
                                >
                                  <img
                                    src={visualLocationFileUrl(
                                      projectId,
                                      activeLocation.location_id,
                                      "look_lock_archive",
                                      name,
                                    )}
                                    alt={name}
                                    className="visual-thumb-img"
                                  />
                                </button>
                              </div>
                            ))}
                          </div>
                        </>
                      )}
                      <div
                        className="row"
                        style={{ flexWrap: "wrap", gap: 8, marginTop: 8 }}
                      >
                        <button
                          type="button"
                          className="btn btn-primary"
                          disabled={
                            busy ||
                            activeLocation.bootstrap_status ===
                              "description_needs_review"
                          }
                          onClick={() => void onConfirmLocationBootstrap()}
                        >
                          确认地点训练集
                        </button>
                        <button
                          type="button"
                          className="btn btn-secondary"
                          disabled={busy}
                          onClick={() => void onSkipLocationBootstrap()}
                        >
                          跳过此地点
                        </button>
                      </div>
                    </div>
                  )}
                  <h4 style={{ marginBottom: 0 }}>候选空镜</h4>
                  <div className="bible-cards visual-thumbs" aria-label="location-candidates">
                    {activeLocation.candidates.map((name) => (
                      <div key={name} className="visual-thumb">
                        <img
                          src={visualLocationFileUrl(
                            projectId,
                            activeLocation.location_id,
                            "candidates",
                            name,
                          )}
                          alt={name}
                          className="visual-thumb-img"
                        />
                      </div>
                    ))}
                  </div>
                  <h4 style={{ marginBottom: 0 }}>扩展空镜</h4>
                  <div className="bible-cards visual-thumbs" aria-label="location-sheets">
                    {(activeLocation.sheets || []).map((name) => (
                      <div key={name} className="visual-thumb">
                        <img
                          src={visualLocationFileUrl(
                            projectId,
                            activeLocation.location_id,
                            "sheets",
                            name,
                          )}
                          alt={name}
                          className="visual-thumb-img"
                        />
                      </div>
                    ))}
                  </div>
                </>
              )}
            </div>
          </div>
        </>
      ) : (
        <>
      <div className="row" style={{ flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={onBootstrap}
        >
          初始化视觉训练集
          {active ? `（${active.name}）` : ""}
        </button>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          onClick={onBootstrapAll}
        >
          全部 major 初始化
        </button>
        <span className="note" style={{ margin: 0 }}>
          自动定妆 + 多姿态训练集，完成后人工确认（不会自动开训 LoRA）
        </span>
      </div>

      <div className="bible-layout visual-layout">
        <nav className="visual-char-nav" aria-label="visual-characters">
          <ul>
            {chars.map((c) => {
              const isActive = c.character_id === activeId;
              const trainLabel =
                c.train_status && c.train_status !== "not_started"
                  ? c.train_status
                  : null;
              return (
                <li key={c.character_id}>
                  <button
                    type="button"
                    className="visual-char-item"
                    aria-current={isActive ? "page" : undefined}
                    onClick={() => setActiveId(c.character_id)}
                  >
                    <span className="visual-char-name">{c.name}</span>
                    <span className="visual-char-stats">
                      候选 {c.candidate_count} · 表 {c.sheet_count ?? 0} · 已选{" "}
                      {c.curated_count}
                    </span>
                    <span className="visual-char-flags">
                      {c.bootstrap_status === "awaiting_confirm" ? (
                        <span className="visual-char-flag">待确认</span>
                      ) : null}
                      {c.lora_ready ? (
                        <span className="visual-char-flag is-ok">LoRA</span>
                      ) : null}
                      {trainLabel ? (
                        <span
                          className={
                            trainLabel === "package_ready" ||
                            trainLabel === "trained" ||
                            trainLabel === "curated_ready"
                              ? "visual-char-flag is-ok"
                              : trainLabel === "failed" ||
                                  trainLabel === "train_failed"
                                ? "visual-char-flag is-bad"
                                : "visual-char-flag"
                          }
                        >
                          {trainLabel}
                        </span>
                      ) : null}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>

        <div className="stack">
          {!active && <p className="note">暂无 major 角色，请先跑通 Story Bible。</p>}
          {active && (
            <>
              <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>
                {active.name}
              </h3>
              <p className="note">
                trigger：<code>{active.trigger}</code> · 状态 {active.status || "—"} ·
                train {active.train_status || "not_started"} · probe{" "}
                {active.probe_status || "not_started"}
                {active.bootstrap_status && active.bootstrap_status !== "not_started"
                  ? ` · bootstrap ${active.bootstrap_status}`
                  : ""}
                {active.lora_ready ? " · lora_ready" : ""}
              </p>
              {jobProgress && (
                <div className="bible-card" aria-label="job-progress">
                  <p className="note" role="status" style={{ marginBottom: 8 }}>
                    {jobProgress.kind === "lora_train" ||
                    jobProgress.kind === "lora_train_batch"
                      ? jobProgress.note || "LoRA 微调进行中…"
                      : jobProgress.kind === "visual_bootstrap"
                        ? jobProgress.note ||
                          `初始化训练集 ${jobProgress.done}/${jobProgress.total}`
                        : jobProgress.note ||
                          `正在出图 ${jobProgress.done}/${jobProgress.total}`}
                    {jobProgress.kind === "lora_train_batch"
                      ? ` · 总进度 ${jobProgress.done}/${jobProgress.total}`
                      : jobProgress.kind === "lora_train"
                        ? "（状态栏会刷新运行秒数）"
                        : jobProgress.kind === "visual_bootstrap"
                          ? jobProgress.step
                            ? ` · 步骤 ${jobProgress.step}`
                            : ""
                          : "（每完成一张会立刻出现在下方）"}
                  </p>
                  {jobProgress.kind === "lora_train_batch" &&
                    (!!jobProgress.items?.length ||
                      !!jobProgress.skipped?.length) && (
                      <ul className="visual-batch-train-list">
                        {(jobProgress.skipped || []).map((it) => (
                          <li key={`skip-${it.character_id}`}>
                            <strong>{it.name}</strong>
                            <span className="visual-char-flag">skipped</span>
                            {it.error ? (
                              <span className="visual-char-stats">{it.error}</span>
                            ) : null}
                            {it.lora_file ? (
                              <span className="visual-char-stats">{it.lora_file}</span>
                            ) : null}
                          </li>
                        ))}
                        {(jobProgress.items || []).map((it) => (
                          <li key={it.character_id}>
                            <strong>{it.name}</strong>
                            <span className={`visual-char-flag ${
                              it.status === "succeeded"
                                ? "is-ok"
                                : it.status === "failed"
                                  ? "is-bad"
                                  : it.status === "running"
                                    ? "is-ok"
                                    : ""
                            }`}>
                              {it.status}
                            </span>
                            {it.lora_file ? (
                              <span className="visual-char-stats">{it.lora_file}</span>
                            ) : null}
                            {it.error ? (
                              <span className="visual-char-stats">{it.error}</span>
                            ) : null}
                          </li>
                        ))}
                      </ul>
                    )}
                </div>
              )}
              {(active.bootstrap_status === "awaiting_confirm" ||
                active.bootstrap_status === "look_lock_needs_review" ||
                active.bootstrap_status === "description_needs_review") && (
                <div className="bible-card" aria-label="bootstrap-review">
                  <h4 style={{ marginTop: 0 }}>训练集待确认</h4>
                  <p className="note">
                    状态：{active.bootstrap_status}
                    {active.look_lock_ready ? " · 已有定妆" : " · 尚未定妆"}
                  </p>
                  {!!(active.bootstrap_warnings || []).length && (
                    <ul className="note">
                      {(active.bootstrap_warnings || []).slice(0, 8).map((w) => (
                        <li key={w}>{w}</li>
                      ))}
                    </ul>
                  )}
                  {!!(active.look_lock_archive || []).length && (
                    <>
                      <p className="note">备选定妆（点选替换）：</p>
                      <div className="bible-cards visual-thumbs" aria-label="lock-archive">
                        {(active.look_lock_archive || []).map((name) => (
                          <div key={name} className="visual-thumb">
                            <button
                              type="button"
                              disabled={busy}
                              onClick={() => void onSwapBootstrapLock(name)}
                              style={{
                                display: "block",
                                width: "100%",
                                padding: 0,
                                border: "1px solid var(--border)",
                                background: "transparent",
                                cursor: "pointer",
                                borderRadius: 8,
                              }}
                              aria-label={`换定妆 ${name}`}
                            >
                              <img
                                src={visualFileUrl(
                                  projectId,
                                  active.character_id,
                                  "look_lock_archive",
                                  name,
                                )}
                                alt={name}
                                className="visual-thumb-img"
                              />
                            </button>
                            <span className="visual-char-stats">{name}</span>
                          </div>
                        ))}
                      </div>
                    </>
                  )}
                  <div className="row" style={{ flexWrap: "wrap", gap: 8, marginTop: 8 }}>
                    <button
                      type="button"
                      className="btn btn-primary"
                      disabled={busy || active.bootstrap_status === "description_needs_review"}
                      onClick={() => void onConfirmBootstrap()}
                    >
                      确认训练集
                    </button>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy}
                      onClick={() => void onSkipBootstrap()}
                    >
                      跳过此角色
                    </button>
                  </div>
                </div>
              )}
              <p className="bible-plain">{active.prompt_zh || "（无 prompt_zh）"}</p>

              <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy || !(active.sheets || []).length}
                  onClick={() => selectAllSheetsForLora()}
                >
                  角色表全选入训
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => void onCurate()}
                >
                  确认训练集
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy || active.curated_count <= 0}
                  onClick={() => void onCheckTrainset()}
                >
                  检查训练集
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy || !trainCheck?.can_train}
                  onClick={() => void onPackage()}
                >
                  导出训练包
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => void onPackageBatch()}
                  title="为所有可训练角色导出训练包"
                >
                  批量导出训练包
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={
                    busy ||
                    !loraTrainConfigured ||
                    !(
                      active.train_status === "package_ready" ||
                      active.status === "package_ready"
                    )
                  }
                  onClick={() => void onTrain()}
                  title={
                    loraTrainConfigured
                      ? "启动当前角色外部 LoRA 训练"
                      : "请先配置 AIVP_LORA_TRAIN_CMD"
                  }
                >
                  开始微调（当前）
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy || !loraTrainConfigured}
                  onClick={() => void onTrainBatch()}
                  title={
                    loraTrainConfigured
                      ? "串行微调未训练角色（已 trained 且有 LoRA 文件的会自动跳过）"
                      : "请先配置 AIVP_LORA_TRAIN_CMD"
                  }
                >
                  统一微调全部就绪
                </button>
              </div>
              {!loraTrainConfigured && (
                <p className="note">
                  微调未就绪：当前未配置 <code>AIVP_LORA_TRAIN_CMD</code>
                  ，点击也不会进入长时间训练。配置 kohya/sd-scripts
                  命令后刷新页面即可。
                </p>
              )}
              {active.train_status === "training" && (
                <p className="note" role="status">
                  角色状态为 training：后台微调可能仍在进行，请查看状态栏进度或
                  lora 目录下的 train_stdout.log。
                </p>
              )}
              {trainCheck && (
                <div className="bible-card" aria-label="trainset-check">
                  <p className="note">
                    训练集质量：{trainCheck.can_train ? "可训练" : "不建议训练"} · 分数{" "}
                    {trainCheck.score}
                  </p>
                  <p className="note">
                    已选 {trainCheck.image_count} · caption {trainCheck.caption_count}/
                    {trainCheck.image_count} · 三视图 {trainCheck.turnaround_count} · 表情{" "}
                    {trainCheck.expression_count} · 候选 {trainCheck.candidate_count}
                  </p>
                  <p className="note">
                    正面 {trainCheck.has_front ? "✓" : "✗"} · 侧面{" "}
                    {trainCheck.has_side ? "✓" : "✗"} · 背面 {trainCheck.has_back ? "✓" : "✗"}
                  </p>
                  {!!trainCheck.warnings.length && (
                    <p className="note">warnings: {trainCheck.warnings.join(", ")}</p>
                  )}
                </div>
              )}

              <h4 style={{ marginBottom: 0 }}>候选图</h4>
              {active.look_lock_ready && (
                <div className="bible-card" aria-label="look-lock-panel">
                  <p className="note" style={{ marginBottom: 8 }}>
                    定妆已锁定：后续候选会<strong>锁住脸与服饰</strong>，只换动作姿势（基础
                    denoise {Number(active.look_lock?.denoise ?? lookLockDenoise).toFixed(2)}）
                  </p>
                  <div className="row" style={{ alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                    <img
                      key={`look-lock-${active.look_lock?.file || ""}-${active.look_lock?.set_at || ""}`}
                      src={`${visualFileUrl(
                        projectId,
                        active.character_id,
                        "look_lock",
                        active.look_lock?.ref_file || "ref.png",
                      )}?v=${encodeURIComponent(
                        active.look_lock?.set_at || active.look_lock?.file || String(Date.now()),
                      )}`}
                      alt="look-lock"
                      className="visual-thumb-img"
                      style={{ width: 96, height: 128 }}
                    />
                    <div className="row" style={{ gap: 6 }}>
                      {(
                        [
                          ["更锁脸服", 0.48],
                          ["平衡", 0.55],
                          ["动作更大", 0.62],
                        ] as const
                      ).map(([label, value]) => (
                        <button
                          key={label}
                          type="button"
                          className={
                            Math.abs(
                              Number(active.look_lock?.denoise ?? lookLockDenoise) - value,
                            ) < 0.01
                              ? "btn btn-primary"
                              : "btn btn-secondary"
                          }
                          disabled={busy || !active.look_lock?.file}
                          onClick={() => {
                            if (active.look_lock?.folder && active.look_lock?.file) {
                              void onSetLookLock(
                                active.look_lock.folder,
                                active.look_lock.file,
                                value,
                              );
                            } else {
                              setLookLockDenoise(value);
                            }
                          }}
                        >
                          {label} {value.toFixed(2)}
                        </button>
                      ))}
                    </div>
                    <button
                      type="button"
                      className="btn btn-secondary"
                      disabled={busy}
                      onClick={() => void onClearLookLock()}
                    >
                      清除定妆
                    </button>
                  </div>
                </div>
              )}
              {!active.look_lock_ready && (
                <p className="note">
                  提示：先生成并挑选一张满意图，点「设为定妆」，再批量生成候选 / 三视图 /
                  表情，性别与着装会稳定很多。
                </p>
              )}
              <div className="row" style={{ flexWrap: "wrap", gap: 8, alignItems: "center" }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={onCandidatesOnce}
                >
                  单次生成候选
                </button>
                <label className="field" style={{ margin: 0, minWidth: 88 }}>
                  批量数量
                  <input
                    type="number"
                    min={1}
                    max={100}
                    value={batchCount}
                    disabled={busy}
                    aria-label="batch-count"
                    onChange={(e) => setBatchCount(Number(e.target.value) || 1)}
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={onCandidatesBatch}
                >
                  批量生成候选（
                  {Math.max(1, Math.min(100, Math.floor(Number(batchCount) || 8)))}
                  ）
                </button>
                {jobProgress && (
                  <span className="note" style={{ margin: 0 }}>
                    生成中 {jobProgress.done}/{jobProgress.total}
                  </span>
                )}
              </div>
              <div className="bible-cards visual-thumbs" aria-label="candidate-grid">
                {active.candidates.map((name) =>
                  renderThumb(
                    "candidates",
                    name,
                    name,
                    <div className="row" style={{ marginBottom: 8 }}>
                      <input
                        type="checkbox"
                        checked={Boolean(selected[name])}
                        onChange={(e) =>
                          setSelected((prev) => ({ ...prev, [name]: e.target.checked }))
                        }
                      />
                      <span>加入训练集</span>
                    </div>,
                  ),
                )}
              </div>

              <h4 style={{ marginBottom: 0 }}>三视图（LoRA）</h4>
              <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => onTurnaroundOnce("turnaround_front")}
                >
                  单次·正面
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => onTurnaroundOnce("turnaround_side")}
                >
                  单次·侧面
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => onTurnaroundOnce("turnaround_back")}
                >
                  单次·背面
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={onTurnaroundBatch}
                >
                  批量·三视图全部
                </button>
              </div>

              <h4 style={{ marginBottom: 0 }}>表情（剧情维度 / LoRA）</h4>
              {active.expression_dims && active.expression_dims.length > 0 ? (
                <p className="note" style={{ marginTop: 0 }}>
                  来自 Story Bible 的 {expressionButtons.length} 个表情维度
                  {active.default_expression
                    ? ` · 定妆默认：${active.default_expression}`
                    : ""}
                </p>
              ) : (
                <p className="note" style={{ marginTop: 0 }}>
                  尚未从剧情聚类表情维度，当前显示通用 8 槽。可点「从剧情重建表情维度」。
                </p>
              )}
              <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                {expressionButtons.map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    className="btn btn-primary"
                    disabled={busy}
                    onClick={() => onExpressionOnce(key)}
                    title={
                      (active.expression_dims || []).find((d) => d.id === key)
                        ?.evidence?.[0]?.text || key
                    }
                  >
                    单次·{label}
                  </button>
                ))}
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => void onRebuildExpressionDims()}
                >
                  从剧情重建表情维度
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={onExpressionBatch}
                >
                  批量·全部表情
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={onSheetsAll}
                >
                  批量·三视图+表情全套
                </button>
              </div>

              <h4 style={{ marginBottom: 0 }}>角色表预览（勾选入训）</h4>
              <p className="note">
                单次/批量生成的图会出现在下方；勾选后点「确认训练集」写入 curated。
              </p>
              <div className="bible-cards visual-thumbs" aria-label="sheet-grid">
                {(active.sheets || []).map((name) =>
                  renderThumb(
                    "sheets",
                    name,
                    sheetLabel(name),
                    <div className="row" style={{ marginBottom: 8 }}>
                      <input
                        type="checkbox"
                        checked={Boolean(selectedSheets[name])}
                        onChange={(e) =>
                          setSelectedSheets((prev) => ({
                            ...prev,
                            [name]: e.target.checked,
                          }))
                        }
                      />
                      <span>加入 LoRA 训练集</span>
                    </div>,
                  ),
                )}
                {!active.sheets?.length && (
                  <p className="note">尚未生成角色表，请用上方单次/批量按钮出图。</p>
                )}
              </div>

              <div className="stack" style={{ marginTop: 8 }}>
                <label className="field">
                  试生成验证（留空则使用与训练集一致的全身提示词；半身中文默认会被忽略）
                  <input
                    value={probePrompt}
                    onChange={(e) => setProbePrompt(e.target.value)}
                    placeholder="可选附加说明；点验证后显示实际使用的完整提示词"
                    aria-label="probe-prompt"
                  />
                </label>
                <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={
                      busy ||
                      !(
                        active.train_status === "trained" ||
                        Boolean(active.lora_file) ||
                        active.probe_status === "pending" ||
                        active.probe_status === "rejected"
                      )
                    }
                    onClick={() => void onProbe()}
                  >
                    试生成验证
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={
                      busy ||
                      Boolean(active.lora_ready) ||
                      !(
                        active.train_status === "trained" ||
                        active.probe_status === "pending"
                      )
                    }
                    onClick={() => void onApproveLora()}
                  >
                    确认 LoRA 可用
                  </button>
                  <button
                    type="button"
                    className="btn btn-secondary"
                    disabled={busy || active.probe_status === "not_started"}
                    onClick={() => void onRejectLora()}
                  >
                    退回重新训练
                  </button>
                </div>
                {probeResult && active && (
                  <div className="stack">
                    <div className="row">
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() =>
                          setLightbox({ src: probeResult, title: "试生成" })
                        }
                      >
                        放大
                      </button>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        disabled={busy}
                        onClick={() => {
                          const file = probeResult.split("/").pop() || "";
                          if (file) void onDelete("generations", file);
                        }}
                      >
                        删除
                      </button>
                    </div>
                    <button
                      type="button"
                      onClick={() =>
                        setLightbox({ src: probeResult, title: "试生成" })
                      }
                      style={{
                        padding: 0,
                        border: "none",
                        background: "transparent",
                        cursor: "zoom-in",
                        alignSelf: "flex-start",
                      }}
                    >
                      <img
                        src={probeResult}
                        alt="probe"
                        className="visual-probe-preview"
                      />
                    </button>
                  </div>
                )}
              </div>

              {(active.generations || []).length > 0 && (
                <>
                  <h4 style={{ marginBottom: 0 }}>历史试生成</h4>
                  <div className="bible-cards visual-thumbs" aria-label="generations-grid">
                    {(active.generations || []).slice(0, 12).map((name) =>
                      renderThumb("generations", name, name),
                    )}
                  </div>
                </>
              )}
            </>
          )}
          {error && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>
        </>
      )}

      {lightbox && (
        <div
          role="dialog"
          aria-modal="true"
          aria-label={lightbox.title}
          onClick={() => setLightbox(null)}
          style={{
            position: "fixed",
            inset: 0,
            background: "rgba(0,0,0,0.72)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            zIndex: 1000,
            padding: 24,
          }}
        >
          <div
            className="stack"
            onClick={(e) => e.stopPropagation()}
            style={{ maxWidth: "min(960px, 96vw)", maxHeight: "92vh" }}
          >
            <div className="row" style={{ justifyContent: "space-between" }}>
              <strong style={{ color: "#fff" }}>{lightbox.title}</strong>
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => setLightbox(null)}
              >
                关闭
              </button>
            </div>
            <img
              src={lightbox.src}
              alt={lightbox.title}
              style={{
                maxWidth: "100%",
                maxHeight: "80vh",
                objectFit: "contain",
                borderRadius: 8,
              }}
            />
          </div>
        </div>
      )}
    </section>
  );
}
