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
    <section>
      <h2>导出</h2>
      <p>项目：{projectId}</p>
      <button type="button" disabled={busy} onClick={() => void onExport()}>
        {busy ? "导出中…" : "创建导出"}
      </button>
      {error && <p role="alert">{error}</p>}
      {result && (
        <div style={{ marginTop: 12 }}>
          <p>版本：v{String(result.version).padStart(3, "0")}</p>
          <ul>
            <li>
              <a href={result.json} download>
                下载 JSON
              </a>
              <span> — {result.json}</span>
            </li>
            <li>
              <a href={result.md} download>
                下载 Markdown
              </a>
              <span> — {result.md}</span>
            </li>
          </ul>
        </div>
      )}
    </section>
  );
}
