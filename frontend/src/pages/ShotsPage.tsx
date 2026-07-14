import { useEffect, useMemo, useState } from "react";
import { getShots } from "../api/client";

type Shot = {
  shot_id?: string;
  event_id?: string;
  chapter_id?: string;
  order?: number;
  shot_type?: string;
  camera?: string;
  action?: string;
  dialogue?: string;
  duration_sec?: number;
  visual_prompt?: string;
  audio_notes?: string;
  cast?: string[];
  location_name?: string;
};

type Props = {
  projectId: string;
};

export function ShotsPage({ projectId }: Props) {
  const [doc, setDoc] = useState<{
    shots?: Shot[];
    shot_count?: number;
    model?: string;
    warnings?: string[];
  } | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      setError(null);
      try {
        const data = await getShots(projectId);
        setDoc(data);
      } catch (e) {
        setDoc(null);
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [projectId]);

  const groups = useMemo(() => {
    const map = new Map<string, Shot[]>();
    for (const shot of doc?.shots || []) {
      const key = shot.event_id || "unknown";
      const list = map.get(key) || [];
      list.push(shot);
      map.set(key, list);
    }
    return [...map.entries()];
  }, [doc]);

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

  return (
    <section className="panel">
      <h2>分镜脚本</h2>
      <p className="panel-lead">
        由 Story Bible「事件时间线」展开；默认 DeepSeek 生成，可按事件分组浏览。
      </p>
      {doc && (
        <div className="row">
          <span className="note">
            {doc.shot_count ?? doc.shots?.length ?? 0} 镜 · 模型 {doc.model || "—"}
          </span>
          <button type="button" className="btn btn-secondary" onClick={download}>
            导出 JSON
          </button>
        </div>
      )}
      {error && (
        <p className="alert" role="alert">
          {error}
          <span className="note"> （可在流水线点击「生成分镜」）</span>
        </p>
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
                  <article key={shot.shot_id || `${eventId}-${shot.order}`} className="bible-card">
                    <header className="bible-card-head">
                      <h4>
                        #{shot.order} {shot.shot_type || "shot"} · {shot.shot_id}
                      </h4>
                      <span className="tier-pill">{shot.duration_sec ?? "—"}s</span>
                    </header>
                    <dl className="bible-kv">
                      <div>
                        <dt>机位</dt>
                        <dd>{shot.camera || "—"}</dd>
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
                        <dd>{(shot.cast || []).join("、") || "—"}</dd>
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
    </section>
  );
}
