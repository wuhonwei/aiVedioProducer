import { useEffect, useMemo, useState } from "react";
import {
  getBible,
  getBibleMeta,
  lockBibleBlock,
  patchBible,
  reviewBibleBlock,
  type BibleMeta,
} from "../api/client";

const BIBLE_SECTIONS: { key: string; title: string }[] = [
  { key: "project_meta", title: "1. 项目元信息" },
  { key: "logline", title: "2. 故事一句话概括" },
  { key: "worldbuilding", title: "3. 世界观设定" },
  { key: "plot_structure", title: "4. 主线剧情 / 篇章结构" },
  { key: "characters", title: "5. 主要角色 Bible" },
  { key: "character_relations", title: "6. 角色关系" },
  { key: "locations", title: "7. 地点 / 场景 Bible" },
  { key: "factions", title: "8. 组织 / 阵营 / 势力" },
  { key: "props", title: "9. 重要道具 / 法宝 / 物件" },
  { key: "timeline", title: "10. 事件时间线" },
  { key: "foreshadowing", title: "11. 伏笔 / 悬念 / 回收" },
  { key: "adaptation_notes", title: "12. 影视化改编信息" },
  { key: "visual_style", title: "13. 视觉风格 Bible" },
  { key: "character_visuals", title: "14. 角色视觉设定" },
  { key: "voice_bible", title: "15. 声音设定 Voice Bible" },
  { key: "production_constraints", title: "16. 分镜/资产生产约束" },
];

const ASSET_KEYS = new Set(["characters", "locations", "factions", "props"]);

type Props = {
  projectId: string;
};

function formatValue(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string") return value;
  return JSON.stringify(value, null, 2);
}

function parseValue(raw: string, original: unknown): unknown {
  if (typeof original === "string" || original == null) return raw;
  try {
    return JSON.parse(raw) as unknown;
  } catch {
    return raw;
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

function textOf(value: unknown): string {
  if (value == null) return "";
  if (typeof value === "string" || typeof value === "number") return String(value);
  if (Array.isArray(value)) return value.map(textOf).filter(Boolean).join("、");
  return "";
}

function AssetCards({ items, kind }: { items: unknown[]; kind: string }) {
  if (!items.length) {
    return <p className="note">暂无条目。</p>;
  }
  return (
    <div className="bible-cards" aria-label={`${kind}-cards`}>
      {items.map((raw, idx) => {
        const item = asRecord(raw) ?? {};
        const name = textOf(item.name) || `条目 ${idx + 1}`;
        const tier = textOf(item.tier) || "—";
        const prompt = textOf(item.prompt_zh) || textOf(item.brief);
        const appearance = asRecord(item.appearance);
        const wardrobe = asRecord(item.wardrobe);
        const voice = asRecord(item.voice);
        return (
          <article key={`${name}-${idx}`} className="bible-card">
            <header className="bible-card-head">
              <h4>{name}</h4>
              <span className={`tier-pill tier-${tier}`}>{tier}</span>
            </header>
            {kind === "characters" && (
              <dl className="bible-kv">
                <div>
                  <dt>定妆</dt>
                  <dd>
                    {[appearance?.face, appearance?.hair, wardrobe?.default]
                      .map(textOf)
                      .filter(Boolean)
                      .join("；") || "—"}
                  </dd>
                </div>
                <div>
                  <dt>声线</dt>
                  <dd>{textOf(voice?.timbre) || "—"}</dd>
                </div>
              </dl>
            )}
            {kind === "locations" && (
              <dl className="bible-kv">
                <div>
                  <dt>氛围</dt>
                  <dd>{textOf(item.era_mood) || "—"}</dd>
                </div>
                <div>
                  <dt>光色</dt>
                  <dd>{textOf(item.palette) || "—"}</dd>
                </div>
              </dl>
            )}
            {kind === "props" && (
              <dl className="bible-kv">
                <div>
                  <dt>材质</dt>
                  <dd>{textOf(item.material) || "—"}</dd>
                </div>
                <div>
                  <dt>特写</dt>
                  <dd>{textOf(item.closeup_notes) || "—"}</dd>
                </div>
              </dl>
            )}
            {kind === "factions" && (
              <dl className="bible-kv">
                <div>
                  <dt>目标</dt>
                  <dd>{textOf(item.goal) || "—"}</dd>
                </div>
                <div>
                  <dt>色板</dt>
                  <dd>{textOf(item.uniform_palette) || "—"}</dd>
                </div>
              </dl>
            )}
            {prompt && (
              <p className="bible-prompt">
                <strong>prompt</strong> {prompt}
              </p>
            )}
          </article>
        );
      })}
    </div>
  );
}

function TimelineCards({ items }: { items: unknown[] }) {
  if (!items.length) return <p className="note">暂无事件。</p>;
  return (
    <div className="bible-cards" aria-label="timeline-cards">
      {items.map((raw, idx) => {
        const item = asRecord(raw) ?? {};
        return (
          <article key={textOf(item.id) || idx} className="bible-card">
            <header className="bible-card-head">
              <h4>{textOf(item.summary) || `事件 ${idx + 1}`}</h4>
              <span className="tier-pill">{textOf(item.chapter_id) || "—"}</span>
            </header>
            <dl className="bible-kv">
              <div>
                <dt>画面</dt>
                <dd>{textOf(item.visual_beat) || "—"}</dd>
              </div>
              <div>
                <dt>机位</dt>
                <dd>{textOf(item.camera_hint) || "—"}</dd>
              </div>
              <div>
                <dt>出场</dt>
                <dd>{textOf(item.cast) || "—"}</dd>
              </div>
            </dl>
          </article>
        );
      })}
    </div>
  );
}

function ReadableSection({ section, value }: { section: string; value: unknown }) {
  if (ASSET_KEYS.has(section) && Array.isArray(value)) {
    return <AssetCards items={value} kind={section} />;
  }
  if (section === "timeline" && Array.isArray(value)) {
    return <TimelineCards items={value} />;
  }
  if (section === "character_visuals" && Array.isArray(value)) {
    return (
      <div className="bible-cards" aria-label="character-visuals-cards">
        {value.map((raw, idx) => {
          const item = asRecord(raw) ?? {};
          return (
            <article key={idx} className="bible-card">
              <header className="bible-card-head">
                <h4>{textOf(item.name) || `角色 ${idx + 1}`}</h4>
              </header>
              <p className="bible-prompt">{textOf(item.notes) || textOf(item.prompt_zh) || "—"}</p>
            </article>
          );
        })}
      </div>
    );
  }
  if (section === "voice_bible") {
    const rec = asRecord(value) ?? {};
    const cast = Array.isArray(rec.cast) ? rec.cast : [];
    return (
      <div className="stack">
        <p className="note">环境/台词线索：{textOf(rec.cues) || "—"}</p>
        <div className="bible-cards" aria-label="voice-cast-cards">
          {cast.map((raw, idx) => {
            const item = asRecord(raw) ?? {};
            return (
              <article key={idx} className="bible-card">
                <header className="bible-card-head">
                  <h4>{textOf(item.name) || `角色 ${idx + 1}`}</h4>
                </header>
                <p className="bible-prompt">{textOf(item.cue) || "—"}</p>
              </article>
            );
          })}
        </div>
      </div>
    );
  }
  if (typeof value === "string") {
    return <p className="bible-plain">{value || "（空）"}</p>;
  }
  return (
    <pre className="bible-pre" aria-label={`${section}-readable`}>
      {formatValue(value) || "（空）"}
    </pre>
  );
}

export function BiblePage({ projectId }: Props) {
  const [bible, setBible] = useState<Record<string, unknown>>({});
  const [meta, setMeta] = useState<BibleMeta | null>(null);
  const [section, setSection] = useState("logline");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [editJson, setEditJson] = useState(false);

  const refreshMeta = async () => {
    try {
      const m = await getBibleMeta(projectId);
      setMeta(m);
    } catch {
      setMeta(null);
    }
  };

  useEffect(() => {
    void (async () => {
      setError(null);
      try {
        const data = await getBible(projectId);
        setBible(data);
        setDraft(formatValue(data.logline));
        setSection("logline");
        setEditJson(false);
        await refreshMeta();
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [projectId]);

  useEffect(() => {
    setDraft(formatValue(bible[section]));
    setEditJson(false);
  }, [section, bible]);

  const value = bible[section];
  const blockMeta = meta?.blocks?.[section];
  const supportsCards = useMemo(
    () =>
      ASSET_KEYS.has(section) ||
      section === "timeline" ||
      section === "character_visuals" ||
      section === "voice_bible",
    [section],
  );

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const parsed = parseValue(draft, bible[section]);
      const patch = { [section]: parsed };
      const updated = await patchBible(projectId, patch);
      setBible((prev) => ({ ...prev, ...updated, ...patch }));
      setEditJson(false);
      await refreshMeta();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const onReview = async (action: string) => {
    setError(null);
    try {
      const m = await reviewBibleBlock(projectId, { block: section, action });
      setMeta(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const onLock = async (locked: boolean) => {
    setError(null);
    try {
      const m = await lockBibleBlock(projectId, { block: section, locked });
      setMeta(m);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  const isLogline = section === "logline";

  return (
    <section className="panel">
      <h2>Story Bible</h2>
      <p className="panel-lead">
        默认按资产卡阅读；需要改结构化字段时切换「编辑 JSON」，保存只写入 overlay。区块可审核/锁定。
      </p>
      <div className="bible-layout">
        <nav aria-label="bible-sections">
          <ul className="bible-nav">
            {BIBLE_SECTIONS.map((s) => {
              const st = meta?.blocks?.[s.key]?.review_status;
              return (
                <li key={s.key}>
                  <button
                    type="button"
                    aria-current={section === s.key ? "page" : undefined}
                    onClick={() => setSection(s.key)}
                  >
                    {s.title}
                    {st ? ` · ${st}` : ""}
                  </button>
                </li>
              );
            })}
          </ul>
        </nav>
        <div className="stack">
          <div className="row" style={{ justifyContent: "space-between" }}>
            <h3 style={{ margin: 0, fontFamily: "var(--font-display)" }}>
              {BIBLE_SECTIONS.find((s) => s.key === section)?.title}
            </h3>
            {(supportsCards || !isLogline) && (
              <button
                type="button"
                className="btn btn-secondary"
                aria-pressed={editJson}
                onClick={() => setEditJson((v) => !v)}
              >
                {editJson ? "阅读视图" : "编辑 JSON"}
              </button>
            )}
          </div>

          {blockMeta && (
            <p className="note" aria-label="block-review-status">
              状态：{blockMeta.review_status}
              {blockMeta.locked ? "（已锁定）" : ""}
            </p>
          )}

          <div className="row">
            <button type="button" className="btn btn-secondary" onClick={() => void onReview("approve")}>
              通过
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => void onReview("reject")}>
              需修改
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => void onLock(true)}>
              锁定
            </button>
            <button type="button" className="btn btn-secondary" onClick={() => void onLock(false)}>
              解锁
            </button>
          </div>

          {editJson || isLogline ? (
            <textarea
              aria-label={isLogline ? "logline" : section}
              rows={isLogline ? 4 : 16}
              style={
                isLogline
                  ? undefined
                  : { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }
              }
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              disabled={Boolean(blockMeta?.locked)}
            />
          ) : (
            <ReadableSection section={section} value={value} />
          )}

          {(editJson || isLogline) && (
            <div className="row">
              <button
                type="button"
                className="btn btn-primary"
                disabled={saving || Boolean(blockMeta?.locked)}
                onClick={() => void onSave()}
              >
                {saving ? "保存中…" : "保存"}
              </button>
            </div>
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
