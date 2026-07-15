import { useEffect, useState } from "react";
import {
  curateVisualCharacter,
  getVisualJob,
  listVisualCharacters,
  startVisualCandidates,
  trainVisualLora,
  visualFileUrl,
  visualT2I,
  type VisualCharacter,
} from "../api/client";

type Props = { projectId: string };

const PROBE_FRAMING = "半身中景，国风光影";

/** Scene/framing prompt for t2i probe; prefer character look text when available. */
export function defaultProbePrompt(c: Pick<VisualCharacter, "name" | "prompt_zh">): string {
  const look = (c.prompt_zh || "").trim();
  if (look) return `${look}，${PROBE_FRAMING}`;
  return `${c.name}，${PROBE_FRAMING}`;
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
    for (let i = 0; i < 120; i++) {
      const j = await getVisualJob(projectId, jobId);
      if (j.status === "succeeded" || j.status === "failed") return j;
      await new Promise((r) => setTimeout(r, 500));
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
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <h2>角色视觉 / LoRA</h2>
      <p className="panel-lead">
        仅 major 角色：自动出候选图 → 勾选训练集 → 准备/训练 LoRA。当前后端：
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
                    · 候选{c.candidate_count}/已选{c.curated_count}
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

              <div className="bible-cards" aria-label="candidate-grid">
                {active.candidates.map((name) => (
                  <label key={name} className="bible-card" style={{ cursor: "pointer" }}>
                    <div className="row" style={{ marginBottom: 8 }}>
                      <input
                        type="checkbox"
                        checked={Boolean(selected[name])}
                        onChange={(e) =>
                          setSelected((prev) => ({ ...prev, [name]: e.target.checked }))
                        }
                      />
                      <span>{name}</span>
                    </div>
                    <img
                      src={visualFileUrl(
                        projectId,
                        active.character_id,
                        "candidates",
                        name,
                      )}
                      alt={name}
                      style={{ width: "100%", borderRadius: 8, display: "block" }}
                    />
                  </label>
                ))}
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
                {probeResult && (
                  <img
                    src={probeResult}
                    alt="probe"
                    style={{ maxWidth: 360, borderRadius: 12, border: "1px solid var(--line)" }}
                  />
                )}
              </div>
            </>
          )}
          {error && (
            <p className="alert" role="alert">
              {error}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
