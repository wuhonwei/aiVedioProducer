import { useEffect, useState, type ReactNode } from "react";
import {
  approveVisualLora,
  checkVisualTrainset,
  curateVisualCharacter,
  deleteVisualFile,
  getVisualJob,
  listVisualCharacters,
  packageVisualLora,
  probeVisualLora,
  rejectVisualLora,
  startVisualCandidates,
  startVisualLoraTrain,
  startVisualSheets,
  visualFileUrl,
  type VisualCharacter,
} from "../api/client";

type Props = { projectId: string };

const PROBE_FRAMING =
  "solo, 1person, looking at viewer, upper body portrait, simple background, 人物半身特写";

/** Scene/framing prompt for t2i probe; prefer character look text when available. */
export function defaultProbePrompt(c: Pick<VisualCharacter, "name" | "prompt_zh">): string {
  const look = (c.prompt_zh || "").trim();
  if (look) return `${look}，${PROBE_FRAMING}`;
  return `${c.name}，${PROBE_FRAMING}`;
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
  const [chars, setChars] = useState<VisualCharacter[]>([]);
  const [backend, setBackend] = useState("stub");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [selectedSheets, setSelectedSheets] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [probePrompt, setProbePrompt] = useState("");
  const [probeResult, setProbeResult] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<Lightbox>(null);
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
    if (!activeId && data.characters[0]) {
      setActiveId(data.characters[0].character_id);
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

  useEffect(() => {
    if (!active) return;
    const next: Record<string, boolean> = {};
    for (const name of active.candidates) {
      next[name] = active.curated.includes(name);
    }
    setSelected(next);
    const sheets = active.sheets || [];
    const hasCuratedSheets = sheets.some((n) => active.curated.includes(n));
    const sheetsNext: Record<string, boolean> = {};
    for (const name of sheets) {
      // LoRA primary set: default-select all sheets until user has curated some.
      sheetsNext[name] = hasCuratedSheets
        ? active.curated.includes(name)
        : true;
    }
    setSelectedSheets(sheetsNext);
  }, [active]);

  useEffect(() => {
    if (!active) return;
    setProbePrompt(defaultProbePrompt(active));
    setProbeResult(null);
    setTrainCheck(null);
  }, [active?.character_id, active?.prompt_zh, active?.name]);

  const pollJob = async (jobId: string) => {
    for (let i = 0; i < 600; i++) {
      const j = await getVisualJob(projectId, jobId);
      if (j.status === "succeeded" || j.status === "failed") return j;
      await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error("visual job timeout");
  };

  const runVisualJob = async (start: () => Promise<{ id: string }>) => {
    setBusy(true);
    setError(null);
    try {
      const job = await start();
      const done = await pollJob(job.id);
      if (done.status === "failed") throw new Error(done.error || "visual job failed");
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

  const onCandidatesBatch = () =>
    void runVisualJob(() =>
      startVisualCandidates(projectId, {
        character_ids: activeId ? [activeId] : undefined,
        count: 8,
      }),
    );

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

  const onTrain = async () => {
    if (!active) return;
    await runVisualJob(() => startVisualLoraTrain(projectId, active.character_id));
  };

  const onProbe = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      const r = await probeVisualLora(projectId, active.character_id, probePrompt);
      const file = String(r.file || "");
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

  const renderThumb = (
    folder: "candidates" | "sheets" | "generations",
    name: string,
    title: string,
    extra?: ReactNode,
  ) => {
    if (!active) return null;
    const src = visualFileUrl(projectId, active.character_id, folder, name);
    return (
      <div key={`${folder}-${name}`} className="bible-card" style={{ position: "relative" }}>
        <div className="row" style={{ marginBottom: 8, justifyContent: "space-between" }}>
          <span>{title}</span>
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
        <button
          type="button"
          onClick={() => setLightbox({ src, title })}
          style={{
            display: "block",
            width: "100%",
            padding: 0,
            border: "none",
            background: "transparent",
            cursor: "zoom-in",
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
      <h2>角色视觉 / LoRA</h2>
      <p className="panel-lead">
        仅 major 角色：候选 / 三视图 / 表情均可<strong>多次点击追加生成</strong>
        （不覆盖旧图）。勾选后「确认训练集」→「训练 / 导出包」。当前后端：
        <strong> {backend}</strong>
        {backend === "stub" ? "（占位出图，接好 Comfy 后改 AIVP_IMAGE_BACKEND=comfy）" : ""}。
      </p>

      <div className="bible-layout">
        <nav aria-label="visual-characters">
          <ul className="bible-nav">
            {chars.map((c) => (
              <li key={c.character_id}>
                <button
                  type="button"
                  aria-current={c.character_id === activeId ? "page" : undefined}
                  onClick={() => setActiveId(c.character_id)}
                >
                  {c.name}
                  <span className="note">
                    {" "}
                    · 候选{c.candidate_count}/表{c.sheet_count ?? 0}/已选{c.curated_count}
                    {c.lora_ready ? " · LoRA✓" : ""}
                    {c.train_status && c.train_status !== "not_started"
                      ? ` · ${c.train_status}`
                      : ""}
                  </span>
                </button>
              </li>
            ))}
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
                {active.lora_ready ? " · lora_ready" : ""}
              </p>
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
                  className="btn btn-primary"
                  disabled={
                    busy ||
                    !(
                      active.train_status === "package_ready" ||
                      active.status === "package_ready"
                    )
                  }
                  onClick={() => void onTrain()}
                >
                  开始微调
                </button>
              </div>
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
              <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={onCandidatesOnce}
                >
                  单次生成候选
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={onCandidatesBatch}
                >
                  批量生成候选（8）
                </button>
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

              <h4 style={{ marginBottom: 0 }}>表情（LoRA）</h4>
              <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
                {(
                  [
                    ["expr_calm", "平静"],
                    ["expr_smile", "微笑"],
                    ["expr_happy", "开心"],
                    ["expr_confused", "疑惑"],
                    ["expr_angry", "愤怒"],
                    ["expr_sad", "悲伤"],
                    ["expr_surprised", "惊讶"],
                    ["expr_shy", "害羞"],
                  ] as const
                ).map(([key, label]) => (
                  <button
                    key={key}
                    type="button"
                    className="btn btn-primary"
                    disabled={busy}
                    onClick={() => onExpressionOnce(key)}
                  >
                    单次·{label}
                  </button>
                ))}
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
                  试生成验证（训练完成后用 trigger 验证 LoRA）
                  <input
                    value={probePrompt}
                    onChange={(e) => setProbePrompt(e.target.value)}
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
