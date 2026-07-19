import { useEffect, useState } from "react";
import { createProject, deleteProject, listProjects, type Project } from "../api/client";

type Props = {
  onSelect: (projectId: string) => void;
  currentProjectId?: string | null;
  onDeleted?: (projectId: string) => void;
};

export function ProjectListPage({ onSelect, onDeleted }: Props) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [name, setName] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [deletingId, setDeletingId] = useState<string | null>(null);

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

  const onDelete = async (p: Project) => {
    const ok = window.confirm(
      `确定删除「${p.name}」？将永久删除该项目全部数据（文本、视觉资产、LoRA、关键帧等），不可恢复。`,
    );
    if (!ok) return;
    setDeletingId(p.id);
    setError(null);
    try {
      await deleteProject(p.id);
      await refresh();
      onDeleted?.(p.id);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setDeletingId(null);
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
            <li key={p.id} className="row" style={{ alignItems: "stretch", gap: 8 }}>
              <button
                type="button"
                style={{ flex: 1, textAlign: "left" }}
                onClick={() => onSelect(p.id)}
              >
                <strong>{p.name}</strong>
                <div style={{ color: "var(--ink-soft)", fontSize: "0.9rem" }}>
                  {p.id}
                </div>
              </button>
              <button
                type="button"
                className="btn btn-danger"
                aria-label={`删除项目 ${p.name}`}
                disabled={creating || deletingId === p.id}
                onClick={(e) => {
                  e.stopPropagation();
                  void onDelete(p);
                }}
              >
                删除
              </button>
            </li>
          ))}
          {projects.length === 0 && <li className="panel-lead">暂无项目</li>}
        </ul>
      )}
    </section>
  );
}
