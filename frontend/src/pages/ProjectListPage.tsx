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
  const [creating, setCreating] = useState(false);

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
    if (!trimmed) {
      setError("请先输入项目名称");
      return;
    }
    setError(null);
    setCreating(true);
    try {
      const p = await createProject(trimmed);
      setName("");
      await refresh();
      onSelect(p.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setCreating(false);
    }
  };

  return (
    <section className="panel">
      <h2>项目</h2>
      <p className="panel-lead">创建名建档后进入流水线；后端任务独立于浏览器运行。</p>

      <div className="row">
        <input
          aria-label="project-name"
          placeholder="新项目名称，例如：仙侠卷一"
          value={name}
          disabled={creating}
          onChange={(e) => setName(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              void onCreate();
            }
          }}
          style={{ flex: 1, minWidth: 220 }}
        />
        <button
          type="button"
          className="btn btn-primary"
          disabled={creating}
          onClick={() => void onCreate()}
        >
          {creating ? "创建中…" : "新建项目"}
        </button>
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}

      {loading ? (
        <p className="panel-lead">加载中…</p>
      ) : (
        <ul className="project-list">
          {projects.map((p) => (
            <li key={p.id}>
              <button type="button" onClick={() => onSelect(p.id)}>
                <strong>{p.name}</strong>
                <div style={{ color: "var(--ink-soft)", fontSize: "0.9rem" }}>
                  {p.id}
                </div>
              </button>
            </li>
          ))}
          {projects.length === 0 && <li className="panel-lead">暂无项目</li>}
        </ul>
      )}
    </section>
  );
}
