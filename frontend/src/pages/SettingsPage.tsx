import { useEffect, useState } from "react";
import { healthOllama, type OllamaHealth } from "../api/client";

const DEFAULT_BASE_URL = "http://127.0.0.1:11434";
const DEFAULT_MODEL = "qwen2.5:14b";

export function SettingsPage() {
  const [health, setHealth] = useState<OllamaHealth | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [baseUrl, setBaseUrl] = useState(
    () => localStorage.getItem("ollama_base_url") ?? DEFAULT_BASE_URL,
  );
  const [model, setModel] = useState(
    () => localStorage.getItem("ollama_model") ?? DEFAULT_MODEL,
  );

  const refresh = async () => {
    setError(null);
    try {
      setHealth(await healthOllama());
    } catch (e) {
      setHealth(null);
      setError(e instanceof Error ? e.message : String(e));
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  const onSaveLocal = () => {
    localStorage.setItem("ollama_base_url", baseUrl);
    localStorage.setItem("ollama_model", model);
  };

  return (
    <section>
      <h2>设置</h2>
      <p>后端 Ollama 配置由环境变量控制；以下为控制台默认值（可写 localStorage）。</p>

      <div style={{ display: "grid", gap: 8, maxWidth: 480, marginBottom: 16 }}>
        <label>
          Ollama URL
          <input
            aria-label="ollama-url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            style={{ width: "100%" }}
          />
        </label>
        <label>
          默认模型
          <input
            aria-label="ollama-model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
            style={{ width: "100%" }}
          />
        </label>
        <button type="button" onClick={onSaveLocal}>
          保存到本地
        </button>
      </div>

      <h3>Health</h3>
      <button type="button" onClick={() => void refresh()}>
        刷新健康检查
      </button>
      {error && <p role="alert">{error}</p>}
      {health && (
        <ul>
          <li>ok: {String(health.ok)}</li>
          <li>base_url: {health.base_url}</li>
          <li>model: {health.model}</li>
        </ul>
      )}
      {!health && !error && <p>检查中…</p>}
    </section>
  );
}
