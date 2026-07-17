import { useEffect, useMemo, useState } from "react";
import {
  getAssetPlan,
  patchAssetPlanEntry,
  regenerateAssetPlan,
} from "../api/client";

type AssetItem = {
  id?: string;
  name?: string;
  shot_ids?: string[];
  source_shots?: string[];
  shot_count?: number;
  priority?: string;
  status?: string;
  needs_lora?: boolean;
  needs_concept_art?: boolean;
  needs_reference?: boolean;
  needs_reference_set?: boolean;
};

type Props = {
  projectId: string;
  onOpenShot?: (shotId: string) => void;
};

type Tab = "characters" | "locations" | "props";

export function AssetPlanPage({ projectId, onOpenShot }: Props) {
  const [plan, setPlan] = useState<{
    generated_from?: Record<string, unknown>;
    characters?: AssetItem[];
    locations?: AssetItem[];
    props?: AssetItem[];
  } | null>(null);
  const [tab, setTab] = useState<Tab>("characters");
  const [priority, setPriority] = useState("");
  const [needsOnly, setNeedsOnly] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const reload = async () => {
    setError(null);
    try {
      setPlan(await getAssetPlan(projectId));
    } catch (e) {
      setPlan(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void reload();
  }, [projectId]);

  const items = useMemo(() => {
    const raw = (plan?.[tab] || []) as AssetItem[];
    return raw.filter((item) => {
      if (priority && item.priority !== priority) return false;
      if (needsOnly) {
        if (tab === "characters" && !item.needs_lora) return false;
        if (tab === "locations" && !(item.needs_concept_art || item.needs_reference_set))
          return false;
        if (tab === "props" && !item.needs_reference) return false;
      }
      return true;
    });
  }, [plan, tab, priority, needsOnly]);

  const onRegen = async () => {
    setBusy(true);
    try {
      setPlan(await regenerateAssetPlan(projectId, true));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onStatus = async (item: AssetItem, status: string) => {
    const id = item.id || item.name;
    if (!id) return;
    setBusy(true);
    try {
      await patchAssetPlanEntry(projectId, tab, id, { status });
      await reload();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <h2>资产计划</h2>
      <p className="panel-lead">
        从已通过 / 已锁定分镜汇总角色、地点、道具需求；可筛选并修改审核状态。
      </p>
      <div className="row" style={{ flexWrap: "wrap", gap: 8 }}>
        <button
          type="button"
          className={`btn ${tab === "characters" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setTab("characters")}
        >
          角色
        </button>
        <button
          type="button"
          className={`btn ${tab === "locations" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setTab("locations")}
        >
          地点
        </button>
        <button
          type="button"
          className={`btn ${tab === "props" ? "btn-primary" : "btn-secondary"}`}
          onClick={() => setTab("props")}
        >
          道具
        </button>
        <label>
          priority{" "}
          <select
            aria-label="filter-priority"
            value={priority}
            onChange={(e) => setPriority(e.target.value)}
          >
            <option value="">全部</option>
            <option value="high">high</option>
            <option value="medium">medium</option>
            <option value="low">low</option>
          </select>
        </label>
        <label>
          <input
            type="checkbox"
            checked={needsOnly}
            onChange={(e) => setNeedsOnly(e.target.checked)}
          />{" "}
          仅 needs_*
        </label>
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          onClick={() => void onRegen()}
        >
          按已通过镜头重算
        </button>
      </div>
      {plan?.generated_from && (
        <p className="note">
          来源：{String(plan.generated_from.shot_review_status || "—")} · shot_count{" "}
          {String(plan.generated_from.shot_count ?? "—")}
        </p>
      )}
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      <div className="stack" style={{ marginTop: 12 }}>
        {items.map((item) => {
          const shotIds = item.shot_ids || item.source_shots || [];
          return (
            <article key={String(item.id || item.name)} className="bible-card">
              <header className="bible-card-head">
                <h4>
                  {item.name} <span className="note">({item.id || "—"})</span>
                </h4>
                <span className="tier-pill">
                  {item.priority || "—"} · {item.status || "pending"}
                </span>
              </header>
              <p className="note">
                shots: {item.shot_count ?? shotIds.length} ·{" "}
                {tab === "characters" && `needs_lora=${Boolean(item.needs_lora)}`}
                {tab === "locations" &&
                  `needs_concept_art=${Boolean(item.needs_concept_art || item.needs_reference_set)}`}
                {tab === "props" && `needs_reference=${Boolean(item.needs_reference)}`}
              </p>
              <p className="note">
                shot_ids:{" "}
                {shotIds.length
                  ? shotIds.map((sid) => (
                      <button
                        key={sid}
                        type="button"
                        className="btn btn-secondary"
                        style={{ marginRight: 4, marginBottom: 4 }}
                        onClick={() => onOpenShot?.(sid)}
                      >
                        {sid}
                      </button>
                    ))
                  : "—"}
              </p>
              <div className="row" style={{ gap: 8 }}>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => void onStatus(item, "approved")}
                >
                  标记通过
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => void onStatus(item, "pending")}
                >
                  待处理
                </button>
                <button
                  type="button"
                  className="btn btn-secondary"
                  disabled={busy}
                  onClick={() => void onStatus(item, "rejected")}
                >
                  跳过
                </button>
              </div>
            </article>
          );
        })}
        {!items.length && <p className="note">暂无资产。请先审核通过若干分镜后重算。</p>}
      </div>
    </section>
  );
}
