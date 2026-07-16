import { useEffect, useState, type ReactNode } from "react";
import {
  curateVisualCharacter,
  deleteVisualFile,
  getVisualJob,
  listVisualCharacters,
  startVisualCandidates,
  startVisualSheets,
  trainVisualLora,
  visualFileUrl,
  visualT2I,
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
  const key = filename.replace(/\.png$/i, "");
  return map[key] || filename;
}

export function VisualPage({ projectId }: Props) {
  const [chars, setChars] = useState<VisualCharacter[]>([]);
  const [backend, setBackend] = useState("stub");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [selected, setSelected] = useState<Record<string, boolean>>({});
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [probePrompt, setProbePrompt] = useState("");
  const [probeResult, setProbeResult] = useState<string | null>(null);
  const [lightbox, setLightbox] = useState<Lightbox>(null);

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
  }, [active]);

  useEffect(() => {
    if (!active) return;
    setProbePrompt(defaultProbePrompt(active));
    setProbeResult(null);
  }, [active?.character_id, active?.prompt_zh, active?.name]);

  const pollJob = async (jobId: string) => {
    for (let i = 0; i < 600; i++) {
      const j = await getVisualJob(projectId, jobId);
      if (j.status === "succeeded" || j.status === "failed") return j;
      await new Promise((r) => setTimeout(r, 1000));
    }
    throw new Error("visual job timeout");
  };

  const onGenerate = async () => {
    setBusy(true);
    setError(null);
    try {
      const job = await startVisualCandidates(projectId, {
        character_ids: activeId ? [activeId] : undefined,
        count: 8,
      });
      const done = await pollJob(job.id);
      if (done.status === "failed") throw new Error(done.error || "candidates failed");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onSheets = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      const job = await startVisualSheets(projectId, active.character_id);
      const done = await pollJob(job.id);
      if (done.status === "failed") throw new Error(done.error || "sheets failed");
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onCurate = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      const keep = Object.entries(selected)
        .filter(([, v]) => v)
        .map(([k]) => k);
      await curateVisualCharacter(projectId, active.character_id, keep);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onTrain = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      await trainVisualLora(projectId, [active.character_id]);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onProbe = async () => {
    if (!active) return;
    setBusy(true);
    setError(null);
    try {
      const r = await visualT2I(projectId, {
        character_id: active.character_id,
        prompt: probePrompt,
      });
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
            style={{ width: "100%", borderRadius: 8, display: "block" }}
          />
        </button>
      </div>
    );
  };

  return (
    <section className="panel">
      <h2>角色视觉 / LoRA</h2>
      <p className="panel-lead">
        仅 major 角色：候选图 → 角色表（三视图/表情）→ 训练集 → LoRA。当前后端：
        <strong> {backend}</strong>
        {backend === "stub" ? "（占位出图，接好 ComfyUI 后改 AIVP_IMAGE_BACKEND=comfy）" : ""}。
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
                    {c.lora_ready ? " · LoRA" : ""}
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
                trigger：<code>{active.trigger}</code> · 状态 {active.status || "—"}
              </p>
              <p className="bible-plain">{active.prompt_zh || "（无 prompt_zh）"}</p>

              <div className="row">
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => void onGenerate()}
                >
                  生成候选图
                </button>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => void onSheets()}
                >
                  生成角色表
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
                  disabled={busy}
                  onClick={() => void onTrain()}
                >
                  训练 / 导出包
                </button>
              </div>

              <h4 style={{ marginBottom: 0 }}>候选图</h4>
              <div className="bible-cards" aria-label="candidate-grid">
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

              <h4 style={{ marginBottom: 0 }}>角色表（三视图 / 表情）</h4>
              <div className="bible-cards" aria-label="sheet-grid">
                {(active.sheets || []).map((name) =>
                  renderThumb("sheets", name, sheetLabel(name)),
                )}
                {!active.sheets?.length && (
                  <p className="note">尚未生成角色表，点击「生成角色表」。</p>
                )}
              </div>

              <div className="stack" style={{ marginTop: 8 }}>
                <label className="field">
                  试生成 prompt（含角色定妆；trigger 仍会自动附加）
                  <input
                    value={probePrompt}
                    onChange={(e) => setProbePrompt(e.target.value)}
                    aria-label="probe-prompt"
                  />
                </label>
                <button
                  type="button"
                  className="btn btn-primary"
                  disabled={busy}
                  onClick={() => void onProbe()}
                >
                  试生成（自动带 trigger）
                </button>
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
                        style={{
                          maxWidth: 360,
                          borderRadius: 12,
                          border: "1px solid var(--line)",
                          display: "block",
                        }}
                      />
                    </button>
                  </div>
                )}
              </div>

              {(active.generations || []).length > 0 && (
                <>
                  <h4 style={{ marginBottom: 0 }}>历史试生成</h4>
                  <div className="bible-cards" aria-label="generations-grid">
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
