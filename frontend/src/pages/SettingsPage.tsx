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
    <section className="panel">
      <h2>设置</h2>
      <p className="panel-lead">
        后端 Ollama 实际取值来自环境变量 / `.env`；此处本地值仅作控制台备忘。
      </p>

      <div className="stack" style={{ maxWidth: 480, marginBottom: 16 }}>
        <label className="field">
          Ollama URL
          <input
            aria-label="ollama-url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
          />
        </label>
        <label className="field">
          默认模型
          <input
            aria-label="ollama-model"
            value={model}
            onChange={(e) => setModel(e.target.value)}
          />
        </label>
        <div className="row">
          <button type="button" className="btn btn-secondary" onClick={onSaveLocal}>
            保存到本地
          </button>
          <button type="button" className="btn btn-primary" onClick={() => void refresh()}>
            刷新健康检查
          </button>
        </div>
      </div>

      {error && (
        <p className="alert" role="alert">
          {error}
        </p>
      )}
      {health && (
        <div className="status-card">
          <div>
            状态：
            <span className={`status-pill ${health.ok ? "is-succeeded" : "is-failed"}`}>
              {health.ok ? "可用" : "不可用"}
            </span>
          </div>
          <div>base_url：{health.base_url}</div>
          <div>model：{health.model}</div>
        </div>
      )}
      {!health && !error && <p className="panel-lead">检查中…</p>}
    </section>
  );
}
