import { useEffect, useState } from "react";
import { createProject, listProjects, type Project } from "../api/client";

type Props = {
  onSelect: (projectId: string) => void;
};

export function ProjectListPage({ onSelect }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const refresh = async () => {
    setLoading(true);
    setError(null);
    try {
      setProjects(await listProjects());
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const onCreate = async () => {
    const trimmed = name.trim();
    if (!trimmed) return;
    setError(null);
    try {
      const p = await createProject(trimmed);
      setName("");
      await refresh();
      onSelect(p.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <section>
      <h2>项目列表</h2>
      <div style={{ display: "flex", gap: 8, marginBottom: 12 }}>
        <input
          aria-label="project-name"
          placeholder="新项目名称"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />
        <button type="button" onClick={() => void onCreate()}>
          新建项目
        </button>
      </div>
      {error && <p role="alert">{error}</p>}
      {loading ? (
        <p>加载中…</p>
      ) : (
        <ul>
          {projects.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => onSelect(p.id)}>
                {p.name} ({p.id})
              </button>
            </li>
          ))}
          {projects.length === 0 && <li>暂无项目</li>}
        </ul>
      )}
    </section>
  );
}
