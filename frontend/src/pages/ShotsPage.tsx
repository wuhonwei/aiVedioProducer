import { useEffect, useMemo, useState } from "react";
import {
  exportShotsYaml,
  getAssetPlan,
  getShots,
  patchShot,
  regenerateAssetPlan,
  reviewShot,
} from "../api/client";

type Shot = {
  shot_id?: string;
  event_id?: string;
  chapter_id?: string;
  order?: number;
  shot_type?: string;
  camera?: string | Record<string, unknown>;
  action?: string;
  dialogue?: string | null;
  duration_sec?: number;
  visual_prompt?: string;
  audio_notes?: string;
  cast?: string[];
  characters?: string[];
  location_name?: string;
  location?: string;
  assets_required?: {
    characters?: string[];
    locations?: string[];
    props?: string[];
    style?: string[];
  };
  review?: { status?: string; notes?: string[] };
};

type Props = {
  projectId: string;
};

function cameraText(camera: Shot["camera"]): string {
  if (!camera) return "—";
  if (typeof camera === "string") return camera;
  const notes = typeof camera.notes === "string" ? camera.notes : "";
  const size = typeof camera.shot_size === "string" ? camera.shot_size : "";
  return [size, notes].filter(Boolean).join(" · ") || "—";
}

export function ShotsPage({ projectId }: Props) {
  const [doc, setDoc] = useState<{
    shots?: Shot[];
    shot_count?: number;
    model?: string;
    warnings?: string[];
    schema_version?: number;
  } | null>(null);
  const [plan, setPlan] = useState<{
    characters?: Array<Record<string, unknown>>;
    locations?: Array<Record<string, unknown>>;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draftPrompt, setDraftPrompt] = useState("");
  const [shots, setShots] = useState<Shot[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const pageSize = 50;

  const reload = async () => {
    setError(null);
    try {
      const data = await getShots(projectId, { offset: 0, limit: pageSize });
      const list = (data.items || data.shots || []) as Shot[];
      setShots(list);
      setTotalCount(data.total_count ?? data.shot_count ?? list.length);
      setHasMore(Boolean(data.has_more));
      setDoc({
        shots: list,
        shot_count: data.total_count ?? data.shot_count,
        model: data.model,
        warnings: data.warnings,
        schema_version: data.schema_version,
      });
      try {
        setPlan(await getAssetPlan(projectId));
      } catch {
        setPlan(null);
      }
    } catch (e) {
      setDoc(null);
      setShots([]);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const loadMore = async () => {
    setLoadingMore(true);
    try {
      const data = await getShots(projectId, { offset: shots.length, limit: pageSize });
      const list = (data.items || data.shots || []) as Shot[];
      setShots((prev) => [...prev, ...list]);
      setTotalCount(data.total_count ?? data.shot_count ?? shots.length + list.length);
      setHasMore(Boolean(data.has_more));
      setDoc((prev) =>
        prev
          ? {
              ...prev,
              shots: [...(prev.shots || []), ...list],
              shot_count: data.total_count ?? data.shot_count,
            }
          : prev,
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    void reload();
  }, [projectId]);

  const groups = useMemo(() => {
    const map = new Map<string, Shot[]>();
    for (const shot of shots) {
      const key = shot.event_id || "unknown";
      const list = map.get(key) || [];
      list.push(shot);
      map.set(key, list);
    }
    return [...map.entries()];
  }, [shots]);

  const selected = shots.find((s) => s.shot_id === selectedId) || null;

  useEffect(() => {
    setDraftPrompt(selected?.visual_prompt || "");
  }, [selectedId, selected?.visual_prompt]);

  const download = () => {
    if (!doc) return;
    const blob = new Blob([JSON.stringify(doc, null, 2)], {
      type: "application/json;charset=utf-8",
    });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `shot_script_${projectId}.json`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const onApprove = async (shotId: string, status: string) => {
    try {
      await reviewShot(projectId, shotId, { status });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onSavePrompt = async () => {
    if (!selectedId) return;
    try {
      await patchShot(projectId, selectedId, { visual_prompt: draftPrompt });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onExportYaml = async () => {
    try {
      await exportShotsYaml(projectId);
      await regenerateAssetPlan(projectId);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section className="panel">
      <h2>分镜脚本</h2>
      <p className="panel-lead">
        生产级 shot schema v2：可审核、编辑 visual_prompt、导出 YAML，并查看资产计划。
      </p>
      {doc && (
        <div className="row">
          <span className="note">
            已加载 {shots.length} / {totalCount || doc.shot_count || 0} 镜 · schema{" "}
            {doc.schema_version ?? "—"} · 模型 {doc.model || "—"}
          </span>
          <button type="button" className="btn btn-secondary" onClick={download}>
            导出 JSON
          </button>
          <button type="button" className="btn btn-secondary" onClick={() => void onExportYaml()}>
            导出 YAML / 刷新资产计划
          </button>
        </div>
      )}
      {error && (
        <p className="alert" role="alert">
          {error}
          <span className="note"> （可在流水线点击「生成分镜」）</span>
        </p>
      )}

      {selected && (
        <div className="bible-card" style={{ marginTop: 12 }}>
          <header className="bible-card-head">
            <h4>编辑 {selected.shot_id}</h4>
            <span className="tier-pill">{selected.review?.status || "needs_review"}</span>
          </header>
          <textarea
            aria-label="visual-prompt"
            rows={4}
            value={draftPrompt}
            onChange={(e) => setDraftPrompt(e.target.value)}
          />
          <div className="row" style={{ marginTop: 8 }}>
            <button type="button" className="btn btn-primary" onClick={() => void onSavePrompt()}>
              保存 visual_prompt
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void onApprove(selected.shot_id!, "approved")}
            >
              通过
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void onApprove(selected.shot_id!, "rejected")}
            >
              驳回
            </button>
          </div>
          <p className="note">
            资产：{(selected.assets_required?.characters || []).join("、") || "—"} /{" "}
            {(selected.assets_required?.locations || []).join("、") || "—"}
          </p>
        </div>
      )}

      {plan && (
        <div className="bible-card" style={{ marginTop: 12 }} aria-label="asset-plan">
          <header className="bible-card-head">
            <h4>资产计划</h4>
          </header>
          <p className="note">
            角色：
            {(plan.characters || [])
              .slice(0, 8)
              .map((c) => `${String(c.name)}(${String(c.shot_count)})`)
              .join("、") || "—"}
          </p>
          <p className="note">
            场景：
            {(plan.locations || [])
              .slice(0, 8)
              .map((c) => `${String(c.name)}(${String(c.shot_count)})`)
              .join("、") || "—"}
          </p>
        </div>
      )}

      <div className="stack" style={{ marginTop: 12 }}>
        {groups.map(([eventId, shots]) => (
          <section key={eventId} className="bible-card">
            <header className="bible-card-head">
              <h4>事件 {eventId}</h4>
              <span className="tier-pill">{shots.length} 镜</span>
            </header>
            <div className="bible-cards">
              {shots
                .slice()
                .sort((a, b) => (a.order || 0) - (b.order || 0))
                .map((shot) => (
                  <article
                    key={shot.shot_id || `${eventId}-${shot.order}`}
                    className="bible-card"
                    style={{
                      outline:
                        selectedId === shot.shot_id ? "2px solid var(--accent, #888)" : undefined,
                      cursor: "pointer",
                    }}
                    onClick={() => setSelectedId(shot.shot_id || null)}
                  >
                    <header className="bible-card-head">
                      <h4>
                        #{shot.order} {shot.shot_type || "shot"} · {shot.shot_id}
                      </h4>
                      <span className="tier-pill">
                        {shot.duration_sec ?? "—"}s · {shot.review?.status || "needs_review"}
                      </span>
                    </header>
                    <dl className="bible-kv">
                      <div>
                        <dt>机位</dt>
                        <dd>{cameraText(shot.camera)}</dd>
                      </div>
                      <div>
                        <dt>动作</dt>
                        <dd>{shot.action || "—"}</dd>
                      </div>
                      <div>
                        <dt>对白</dt>
                        <dd>{shot.dialogue || "—"}</dd>
                      </div>
                      <div>
                        <dt>出场</dt>
                        <dd>
                          {(shot.characters || shot.cast || []).join("、") || "—"}
                        </dd>
                      </div>
                      <div>
                        <dt>资产</dt>
                        <dd>
                          {(shot.assets_required?.characters || []).join("、") || "—"} |{" "}
                          {(shot.assets_required?.locations || []).join("、") ||
                            shot.location ||
                            shot.location_name ||
                            "—"}
                        </dd>
                      </div>
                    </dl>
                    {shot.visual_prompt && (
                      <p className="bible-prompt">
                        <strong>visual</strong> {shot.visual_prompt}
                      </p>
                    )}
                  </article>
                ))}
            </div>
          </section>
        ))}
      </div>
      {hasMore && (
        <div className="row" style={{ marginTop: 12 }}>
          <button
            type="button"
            className="btn btn-secondary"
            disabled={loadingMore}
            onClick={() => void loadMore()}
          >
            {loadingMore ? "加载中…" : "加载更多分镜"}
          </button>
        </div>
      )}
    </section>
  );
}
