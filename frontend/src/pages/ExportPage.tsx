import { useState } from "react";
import { createExport, type ExportResult } from "../api/client";

type Props = {
  projectId: string;
};

export function ExportPage({ projectId }: Props) {
  const [result, setResult] = useState<ExportResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onExport = async () => {
    setBusy(true);
    setError(null);
    try {
      setResult(await createExport(projectId));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="panel">
      <h2>导出</h2>
      <p className="panel-lead">固化版本化 Story Bible（JSON + Markdown），可重复导出。</p>
      <div className="row">
        <button
          type="button"
          className="btn btn-primary"
          disabled={busy}
          onClick={() => void onExport()}
        >
          {busy ? "导出中…" : "创建导出"}
        </button>
      </div>
      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {result && (
        <div className="status-card" style={{ marginTop: 12 }}>
          <p style={{ margin: 0 }}>
            版本：v{String(result.version).padStart(3, "0")}
          </p>
          <ul style={{ margin: 0, paddingLeft: 18 }}>
            <li>
              <a href={result.json_url} download>
                下载 JSON
              </a>
              <span style={{ color: "var(--ink-soft)" }}> — {result.json_url}</span>
            </li>
            <li>
              <a href={result.md_url} download>
                下载 Markdown
              </a>
              <span style={{ color: "var(--ink-soft)" }}> — {result.md_url}</span>
            </li>
          </ul>
        </div>
      )}
    </section>
  );
}
