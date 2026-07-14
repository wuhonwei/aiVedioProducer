import { useEffect, useState } from "react";
import { ProjectListPage } from "./pages/ProjectListPage";
import { PipelinePage } from "./pages/PipelinePage";
import { BiblePage } from "./pages/BiblePage";
import { ExportPage } from "./pages/ExportPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ShotsPage } from "./pages/ShotsPage";

type Page = "list" | "pipeline" | "bible" | "shots" | "export" | "settings";

const NAV: { id: Page; label: string; needsProject?: boolean }[] = [
  { id: "list", label: "项目" },
  { id: "pipeline", label: "流水线", needsProject: true },
  { id: "bible", label: "Story Bible", needsProject: true },
  { id: "shots", label: "分镜", needsProject: true },
  { id: "export", label: "导出", needsProject: true },
  { id: "settings", label: "设置" },
];

function parseHash(): { page: Page; projectId: string | null } {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [pagePart, idPart] = raw.split("/");
  const page = (pagePart || "list") as Page;
  const allowed = NAV.map((n) => n.id);
  return {
    page: allowed.includes(page) ? page : "list",
    projectId: idPart || null,
  };
}

export default function App() {
  const [{ page, projectId }, setRoute] = useState(parseHash);

  useEffect(() => {
    const onHash = () => setRoute(parseHash());
    window.addEventListener("hashchange", onHash);
    return () => window.removeEventListener("hashchange", onHash);
  }, []);

  const go = (next: Page, id?: string | null) => {
    const pid = id ?? projectId;
    if (next === "list" || next === "settings" || !pid) {
      window.location.hash = `#/${next === "settings" ? "settings" : "list"}`;
    } else {
      window.location.hash = `#/${next}/${pid}`;
    }
  };

  return (
    <div className="app-shell">
      <header className="app-header">
        <div className="brand-block">
          <h1>AIVP Story Bible</h1>
          <p>国风长篇文本层工作台 · 清洗切分 · 结构化抽取 · 可编辑导出</p>
          {projectId && (
            <div className="project-chip">
              <span>当前项目</span>
              <strong>{projectId}</strong>
            </div>
          )}
        </div>
        <nav className="nav-row" aria-label="主导航">
          {NAV.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`nav-btn${page === item.id ? " is-active" : ""}`}
              disabled={Boolean(item.needsProject && !projectId)}
              onClick={() => go(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
      </header>

      {page === "list" && (
        <ProjectListPage
          onSelect={(id) => {
            go("pipeline", id);
          }}
        />
      )}
      {page === "pipeline" && projectId && <PipelinePage projectId={projectId} />}
      {page === "bible" && projectId && <BiblePage projectId={projectId} />}
      {page === "shots" && projectId && <ShotsPage projectId={projectId} />}
      {page === "export" && projectId && <ExportPage projectId={projectId} />}
      {page === "settings" && <SettingsPage />}
      {(page === "pipeline" || page === "bible" || page === "shots" || page === "export") &&
        !projectId && (
        <section className="panel">
          <p className="panel-lead">请先在「项目」页选择或新建一个项目。</p>
        </section>
      )}
    </div>
  );
}
