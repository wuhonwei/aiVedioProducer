import { useEffect, useState } from "react";
import { getBible, patchBible } from "../api/client";

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

export function BiblePage({ projectId }: Props) {
  const [bible, setBible] = useState<Record<string, unknown>>({});
  const [section, setSection] = useState("logline");
  const [draft, setDraft] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    void (async () => {
      setError(null);
      try {
        const data = await getBible(projectId);
        setBible(data);
        setDraft(formatValue(data.logline));
        setSection("logline");
      } catch (e) {
        setError(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [projectId]);

  useEffect(() => {
    setDraft(formatValue(bible[section]));
  }, [section, bible]);

  const onSave = async () => {
    setSaving(true);
    setError(null);
    try {
      const value = parseValue(draft, bible[section]);
      const patch = { [section]: value };
      const updated = await patchBible(projectId, patch);
      setBible((prev) => ({ ...prev, ...updated, ...patch }));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSaving(false);
    }
  };

  const isLogline = section === "logline";

  return (
    <section>
      <h2>Story Bible</h2>
      <div style={{ display: "flex", gap: 16 }}>
        <nav aria-label="bible-sections" style={{ minWidth: 200 }}>
          <ul style={{ listStyle: "none", padding: 0, margin: 0 }}>
            {BIBLE_SECTIONS.map((s) => (
              <li key={s.key}>
                <button
                  type="button"
                  aria-current={section === s.key ? "page" : undefined}
                  onClick={() => setSection(s.key)}
                  style={{
                    width: "100%",
                    textAlign: "left",
                    fontWeight: section === s.key ? 700 : 400,
                  }}
                >
                  {s.title}
                </button>
              </li>
            ))}
          </ul>
        </nav>
        <div style={{ flex: 1 }}>
          <h3>{BIBLE_SECTIONS.find((s) => s.key === section)?.title}</h3>
          {isLogline ? (
            <textarea
              aria-label="logline"
              rows={4}
              style={{ width: "100%" }}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
          ) : (
            <textarea
              aria-label={section}
              rows={16}
              style={{ width: "100%", fontFamily: "monospace" }}
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
            />
          )}
          <div style={{ marginTop: 8 }}>
            <button type="button" disabled={saving} onClick={() => void onSave()}>
              保存
            </button>
          </div>
          {error && <p role="alert">{error}</p>}
        </div>
      </div>
    </section>
  );
}
