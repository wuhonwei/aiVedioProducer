import { useEffect, useState } from "react";
import { ProjectListPage } from "./pages/ProjectListPage";
import { PipelinePage } from "./pages/PipelinePage";
import { BiblePage } from "./pages/BiblePage";
import { ExportPage } from "./pages/ExportPage";
import { SettingsPage } from "./pages/SettingsPage";

type Page = "list" | "pipeline" | "bible" | "export" | "settings";

function parseHash(): { page: Page; projectId: string | null } {
  const raw = window.location.hash.replace(/^#\/?/, "");
  const [pagePart, idPart] = raw.split("/");
  const page = (pagePart || "list") as Page;
  const allowed: Page[] = ["list", "pipeline", "bible", "export", "settings"];
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
    <main style={{ fontFamily: "system-ui, sans-serif", padding: 16 }}>
      <header style={{ marginBottom: 16 }}>
        <h1>AIVP Story Bible</h1>
        <nav style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" onClick={() => go("list")}>
            项目
          </button>
          <button
            type="button"
            disabled={!projectId}
            onClick={() => go("pipeline")}
          >
            流水线
          </button>
          <button type="button" disabled={!projectId} onClick={() => go("bible")}>
            Bible
          </button>
          <button
            type="button"
            disabled={!projectId}
            onClick={() => go("export")}
          >
            导出
          </button>
          <button type="button" onClick={() => go("settings")}>
            设置
          </button>
        </nav>
        {projectId && <p>当前项目：{projectId}</p>}
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
      {page === "export" && projectId && <ExportPage projectId={projectId} />}
      {page === "settings" && <SettingsPage />}
      {(page === "pipeline" || page === "bible" || page === "export") && !projectId && (
        <p>请先选择项目。</p>
      )}
    </main>
  );
}
