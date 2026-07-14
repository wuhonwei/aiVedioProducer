const BASE = "";

export type Project = {
  id: string;
  name: string;
  created_at?: string | null;
  export_version?: number;
};

export type Job = {
  id: string;
  project_id: string;
  status: string;
  current_step: string | null;
  chunks_done: number;
  chunks_total: number;
  error_message?: string | null;
  resume_from_step?: string | null;
  created_at?: string | null;
};

export type ExportResult = {
  version: number;
  json_url: string;
  md_url: string;
};

export type OllamaHealth = {
  ok: boolean;
  base_url: string;
  model: string;
};

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, init);
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<T>;
}

export const createProject = (name: string) =>
  req<Project>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });

export const listProjects = () => req<Project[]>("/api/projects");

export const getProject = (projectId: string) =>
  req<Project>(`/api/projects/${projectId}`);

export const uploadSource = (projectId: string, file: File) => {
  const form = new FormData();
  form.append("file", file);
  return req<{ ok: boolean; path: string; bytes: number }>(
    `/api/projects/${projectId}/source`,
    { method: "POST", body: form },
  );
};

export const startJob = (projectId: string, resumeFromStep?: string | null) =>
  req<Job>(`/api/projects/${projectId}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(
      resumeFromStep != null ? { resume_from_step: resumeFromStep } : {},
    ),
  });

export const getJob = (projectId: string, jobId: string) =>
  req<Job>(`/api/projects/${projectId}/jobs/${jobId}`);

export const getBible = (projectId: string) =>
  req<Record<string, unknown>>(`/api/projects/${projectId}/bible`);

export const patchBible = (projectId: string, patch: Record<string, unknown>) =>
  req<Record<string, unknown>>(`/api/projects/${projectId}/bible`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });

export const createExport = (projectId: string) =>
  req<ExportResult>(`/api/projects/${projectId}/exports`, { method: "POST" });

export const healthOllama = () => req<OllamaHealth>("/api/health/ollama");
