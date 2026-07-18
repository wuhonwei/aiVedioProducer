import { useEffect, useMemo, useRef, useState } from "react";
import {
  exportShotsYaml,
  getAssetPlan,
  getShots,
  listVisualLocations,
  patchShot,
  regenerateAssetPlan,
  reviewShot,
  visualFileUrl,
  visualLocationFileUrl,
  visualT2I,
  type VisualLocation,
} from "../api/client";

type Shot = {
  shot_id?: string;
  event_id?: string;
  chapter_id?: string;
  order?: number;
  shot_type?: string;
  camera?: string | Record<string, unknown>;
  camera_movement?: string;
  lens?: string;
  composition?: string;
  action?: string;
  dialogue?: string | null;
  duration_sec?: number;
  visual_prompt?: string;
  negative_prompt?: string;
  audio_notes?: string;
  cast?: string[];
  characters?: string[];
  props?: string[];
  location_name?: string;
  location?: string;
  location_id?: string;
  locked?: boolean;
  review_status?: string;
  generation_status?: string;
  source_refs?: Array<Record<string, unknown>>;
  assets_required?: {
    characters?: string[];
    locations?: string[];
    props?: string[];
    style?: string[];
  };
  asset_refs?: {
    characters?: string[];
    locations?: string[];
    props?: string[];
  };
  review?: { status?: string; notes?: string[] };
};

type Props = {
  projectId: string;
  onOpenAssets?: () => void;
};

function cameraText(camera: Shot["camera"]): string {
  if (!camera) return "—";
  if (typeof camera === "string") return camera;
  const notes = typeof camera.notes === "string" ? camera.notes : "";
  const size = typeof camera.shot_size === "string" ? camera.shot_size : "";
  return [size, notes].filter(Boolean).join(" · ") || "—";
}

function reviewOf(shot: Shot): string {
  return shot.review_status || shot.review?.status || "needs_review";
}

export function ShotsPage({ projectId, onOpenAssets }: Props) {
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
    props?: Array<Record<string, unknown>>;
  } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [shots, setShots] = useState<Shot[]>([]);
  const [locations, setLocations] = useState<VisualLocation[]>([]);
  const [useLocationLora, setUseLocationLora] = useState(false);
  const [genBusy, setGenBusy] = useState(false);
  const [genPreviewUrl, setGenPreviewUrl] = useState<string | null>(null);
  const genTokenRef = useRef(0);
  const selectedIdRef = useRef<string | null>(null);
  const [totalCount, setTotalCount] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const [filterStatus, setFilterStatus] = useState("");
  const [filterEvent, setFilterEvent] = useState("");
  const [filterChapter, setFilterChapter] = useState("");
  const [draft, setDraft] = useState({
    visual_prompt: "",
    negative_prompt: "",
    duration_sec: 4,
    camera_movement: "",
    lens: "",
    composition: "",
    cast: "",
    location: "",
    props: "",
    audio_notes: "",
  });
  const pageSize = 50;

  const queryOpts = () => ({
    offset: 0,
    limit: pageSize,
    eventId: filterEvent || undefined,
    chapterId: filterChapter || undefined,
    reviewStatus: filterStatus || undefined,
  });

  const reload = async () => {
    setError(null);
    try {
      const data = await getShots(projectId, queryOpts());
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
      const data = await getShots(projectId, {
        ...queryOpts(),
        offset: shots.length,
      });
      const list = (data.items || data.shots || []) as Shot[];
      setShots((prev) => [...prev, ...list]);
      setTotalCount(data.total_count ?? data.shot_count ?? shots.length + list.length);
      setHasMore(Boolean(data.has_more));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    void reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [projectId, filterStatus, filterEvent, filterChapter]);

  useEffect(() => {
    listVisualLocations(projectId)
      .then((data) => setLocations(data.locations || []))
      .catch(() => setLocations([]));
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
  selectedIdRef.current = selectedId;

  const characterNameToId = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of plan?.characters || []) {
      const id = String(item.id ?? "").trim();
      const name = String(item.name ?? "").trim();
      if (id && name) map.set(name, id);
    }
    return map;
  }, [plan]);

  const locationNameToId = useMemo(() => {
    const map = new Map<string, string>();
    for (const item of plan?.locations || []) {
      const id = String(item.id ?? "").trim();
      const name = String(item.name ?? "").trim();
      if (id && name) map.set(name, id);
    }
    return map;
  }, [plan]);

  const resolveCharacterIds = (shot: Shot): string[] => {
    const refIds = (shot.asset_refs?.characters || []).filter(Boolean);
    if (refIds.length) return refIds;
    const names = (shot.cast || shot.characters || []).filter(Boolean);
    return names.map((name) => characterNameToId.get(name) || name);
  };

  const resolveLocationId = (shot: Shot, draftLocation?: string): string | undefined => {
    if (shot.location_id) return shot.location_id;
    const refLoc = (shot.asset_refs?.locations || []).find(Boolean);
    if (refLoc) return refLoc;
    const name = draftLocation || shot.location || shot.location_name;
    if (name) {
      const mapped = locationNameToId.get(name);
      if (mapped) return mapped;
    }
    return undefined;
  };

  useEffect(() => {
    if (!selected) return;
    const cam = typeof selected.camera === "object" && selected.camera ? selected.camera : {};
    setDraft({
      visual_prompt: selected.visual_prompt || "",
      negative_prompt: selected.negative_prompt || "",
      duration_sec: selected.duration_sec ?? 4,
      camera_movement:
        selected.camera_movement ||
        (typeof cam.movement === "string" ? cam.movement : "") ||
        "",
      lens: selected.lens || (typeof cam.lens === "string" ? cam.lens : "") || "",
      composition:
        selected.composition ||
        (typeof cam.composition === "string" ? cam.composition : "") ||
        "",
      cast: (selected.cast || selected.characters || []).join("、"),
      location: selected.location || selected.location_name || "",
      props: (selected.props || selected.assets_required?.props || []).join("、"),
      audio_notes: selected.audio_notes || "",
    });
    setUseLocationLora(false);
    setGenPreviewUrl(null);
  }, [selectedId, selected]);

  const onReview = async (shotId: string, status: string) => {
    try {
      await reviewShot(projectId, shotId, { status });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onSave = async () => {
    if (!selectedId || !selected) return;
    try {
      const cast = draft.cast
        .split(/[、,，]/)
        .map((s) => s.trim())
        .filter(Boolean);
      const props = draft.props
        .split(/[、,，]/)
        .map((s) => s.trim())
        .filter(Boolean);
      const camera =
        typeof selected.camera === "object" && selected.camera
          ? { ...selected.camera }
          : {};
      await patchShot(projectId, selectedId, {
        visual_prompt: draft.visual_prompt,
        negative_prompt: draft.negative_prompt,
        duration_sec: Number(draft.duration_sec) || 4,
        camera_movement: draft.camera_movement,
        lens: draft.lens,
        composition: draft.composition,
        cast,
        characters: cast,
        location: draft.location,
        location_name: draft.location,
        props,
        audio_notes: draft.audio_notes,
        camera: {
          ...camera,
          movement: draft.camera_movement || camera.movement,
          lens: draft.lens || camera.lens,
          composition: draft.composition || camera.composition,
        },
        assets_required: {
          ...(selected.assets_required || {}),
          characters: cast,
          locations: draft.location ? [draft.location] : [],
          props,
        },
      });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onGenerateShot = async () => {
    if (!selectedId || !selected) return;
    const shotIdAtStart = selectedId;
    const token = ++genTokenRef.current;
    setGenBusy(true);
    setGenPreviewUrl(null);
    setError(null);
    try {
      const characterIds = resolveCharacterIds(selected);
      const locationId = resolveLocationId(selected, draft.location);
      const out = await visualT2I(projectId, {
        shot_id: selected.shot_id,
        location_id: locationId || undefined,
        character_ids: characterIds,
        character_id: characterIds[0],
        prompt: draft.visual_prompt || selected.visual_prompt || "",
        use_location_lora: useLocationLora,
      });
      if (genTokenRef.current !== token) return;
      if (selectedIdRef.current !== shotIdAtStart) return;
      const file = String(out.file || "");
      const charIds = (out.character_ids as string[] | undefined) || characterIds;
      const locId = (out.location_id as string | undefined) || locationId;
      if (charIds[0]) {
        setGenPreviewUrl(visualFileUrl(projectId, charIds[0], "generations", file));
      } else if (locId) {
        setGenPreviewUrl(visualLocationFileUrl(projectId, locId, "generations", file));
      }
    } catch (e) {
      if (genTokenRef.current === token && selectedIdRef.current === shotIdAtStart) {
        setError(e instanceof Error ? e.message : String(e));
      }
    } finally {
      if (genTokenRef.current === token) {
        setGenBusy(false);
      }
    }
  };

  const onExportYaml = async (approvedOnly: boolean) => {
    try {
      await exportShotsYaml(projectId, approvedOnly);
      await regenerateAssetPlan(projectId, true);
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const locked = Boolean(selected?.locked || reviewOf(selected || {}) === "locked");
  const resolvedLocationId = selected ? resolveLocationId(selected, draft.location) : undefined;

  return (
    <section className="panel">
      <h2>分镜脚本</h2>
      <p className="panel-lead">
        生产级 shot：可筛选、编辑、审核、锁定，并导出 YAML；资产计划默认仅汇总已通过镜头。
      </p>

      <div className="row" style={{ flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
        <label>
          状态{" "}
          <select
            aria-label="filter-review-status"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="">全部</option>
            <option value="needs_review">待审</option>
            <option value="approved">已通过</option>
            <option value="rejected">已驳回</option>
            <option value="needs_regen">需重生成</option>
            <option value="locked">已锁定</option>
          </select>
        </label>
        <label>
          事件{" "}
          <input
            aria-label="filter-event-id"
            value={filterEvent}
            onChange={(e) => setFilterEvent(e.target.value)}
            placeholder="event_id"
          />
        </label>
        <label>
          章节{" "}
          <input
            aria-label="filter-chapter-id"
            value={filterChapter}
            onChange={(e) => setFilterChapter(e.target.value)}
            placeholder="chapter_id"
          />
        </label>
        <button type="button" className="btn btn-secondary" onClick={() => void reload()}>
          刷新
        </button>
      </div>

      {doc && (
        <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
          <span className="note">
            已加载 {shots.length} / {totalCount || doc.shot_count || 0} 镜 · schema{" "}
            {doc.schema_version ?? "—"} · 模型 {doc.model || "—"}
          </span>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void onExportYaml(false)}
          >
            导出全部 YAML
          </button>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => void onExportYaml(true)}
          >
            仅导出已通过 YAML
          </button>
          {onOpenAssets && (
            <button type="button" className="btn btn-primary" onClick={onOpenAssets}>
              打开完整资产计划
            </button>
          )}
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
            <span className="tier-pill">
              {reviewOf(selected)}
              {locked ? " · locked" : ""} · {selected.generation_status || "not_started"}
            </span>
          </header>
          <label>
            visual_prompt
            <textarea
              aria-label="visual-prompt"
              rows={3}
              value={draft.visual_prompt}
              disabled={locked}
              onChange={(e) => setDraft((d) => ({ ...d, visual_prompt: e.target.value }))}
            />
          </label>
          <label>
            negative_prompt
            <textarea
              aria-label="negative-prompt"
              rows={2}
              value={draft.negative_prompt}
              disabled={locked}
              onChange={(e) => setDraft((d) => ({ ...d, negative_prompt: e.target.value }))}
            />
          </label>
          <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
            <label>
              duration_sec
              <input
                aria-label="duration-sec"
                type="number"
                value={draft.duration_sec}
                disabled={locked}
                onChange={(e) =>
                  setDraft((d) => ({ ...d, duration_sec: Number(e.target.value) || 4 }))
                }
              />
            </label>
            <label>
              camera_movement
              <input
                aria-label="camera-movement"
                value={draft.camera_movement}
                disabled={locked}
                onChange={(e) => setDraft((d) => ({ ...d, camera_movement: e.target.value }))}
              />
            </label>
            <label>
              lens
              <input
                aria-label="lens"
                value={draft.lens}
                disabled={locked}
                onChange={(e) => setDraft((d) => ({ ...d, lens: e.target.value }))}
              />
            </label>
          </div>
          <label>
            composition
            <input
              aria-label="composition"
              value={draft.composition}
              disabled={locked}
              onChange={(e) => setDraft((d) => ({ ...d, composition: e.target.value }))}
            />
          </label>
          <label>
            cast（顿号分隔）
            <input
              aria-label="cast"
              value={draft.cast}
              disabled={locked}
              onChange={(e) => setDraft((d) => ({ ...d, cast: e.target.value }))}
            />
          </label>
          <label>
            location
            <input
              aria-label="location"
              value={draft.location}
              disabled={locked}
              onChange={(e) => setDraft((d) => ({ ...d, location: e.target.value }))}
            />
          </label>
          <label>
            props（顿号分隔）
            <input
              aria-label="props"
              value={draft.props}
              disabled={locked}
              onChange={(e) => setDraft((d) => ({ ...d, props: e.target.value }))}
            />
          </label>
          <label>
            audio_notes
            <input
              aria-label="audio-notes"
              value={draft.audio_notes}
              disabled={locked}
              onChange={(e) => setDraft((d) => ({ ...d, audio_notes: e.target.value }))}
            />
          </label>
          <label className="row" style={{ gap: 8, alignItems: "center" }}>
            <input
              type="checkbox"
              aria-label="use-location-lora"
              checked={useLocationLora}
              disabled={
                !resolvedLocationId ||
                !locations.find((l) => l.location_id === resolvedLocationId)?.lora_ready
              }
              onChange={(e) => setUseLocationLora(e.target.checked)}
            />
            使用地点 LoRA
          </label>
          {resolvedLocationId &&
            !locations.find((l) => l.location_id === resolvedLocationId)?.lora_ready && (
              <p className="note">该地点尚未 lora_ready，无法启用地点 LoRA</p>
            )}
          <div className="row" style={{ marginTop: 8, flexWrap: "wrap", gap: 8, alignItems: "center" }}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={
                genBusy ||
                (!resolveCharacterIds(selected).length && !resolvedLocationId)
              }
              onClick={() => void onGenerateShot()}
            >
              {genBusy ? "生成中…" : "生成镜头图"}
            </button>
            {genPreviewUrl && (
              <img src={genPreviewUrl} alt="shot preview" style={{ maxWidth: 320, marginTop: 8 }} />
            )}
          </div>
          <div className="row" style={{ marginTop: 8, flexWrap: "wrap", gap: 8 }}>
            <button
              type="button"
              className="btn btn-primary"
              disabled={locked}
              onClick={() => void onSave()}
            >
              保存
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void onReview(selected.shot_id!, "approved")}
            >
              通过
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void onReview(selected.shot_id!, "needs_review")}
            >
              退回修改
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void onReview(selected.shot_id!, "rejected")}
            >
              废弃
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void onReview(selected.shot_id!, "needs_regen")}
            >
              需重生成
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void onReview(selected.shot_id!, "locked")}
            >
              锁定
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => void onReview(selected.shot_id!, "needs_review")}
            >
              解锁
            </button>
          </div>
          <p className="note">
            source_refs:{" "}
            {(selected.source_refs || [])
              .map((r) => `${String(r.event_id || "")}:${String(r.evidence || "").slice(0, 40)}`)
              .join(" | ") || "—"}
          </p>
        </div>
      )}

      {plan && (
        <div className="bible-card" style={{ marginTop: 12 }} aria-label="asset-plan">
          <header className="bible-card-head">
            <h4>资产计划摘要</h4>
          </header>
          <p className="note">
            角色：
            {(plan.characters || [])
              .slice(0, 8)
              .map((c) => `${String(c.name)}(${String(c.shot_count || (c.shot_ids as string[] | undefined)?.length || 0)})`)
              .join("、") || "—"}
          </p>
          <p className="note">
            场景：
            {(plan.locations || [])
              .slice(0, 8)
              .map((c) => `${String(c.name)}(${String(c.shot_count || 0)})`)
              .join("、") || "—"}
          </p>
        </div>
      )}

      <div className="stack" style={{ marginTop: 12 }}>
        {groups.map(([eventId, groupShots]) => (
          <section key={eventId} className="bible-card">
            <header className="bible-card-head">
              <h4>事件 {eventId}</h4>
              <span className="tier-pill">{groupShots.length} 镜</span>
            </header>
            <div className="bible-cards">
              {groupShots
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
                        {shot.duration_sec ?? "—"}s · {reviewOf(shot)}
                        {shot.locked ? " · lock" : ""}
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
                        <dt>出场</dt>
                        <dd>{(shot.characters || shot.cast || []).join("、") || "—"}</dd>
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
