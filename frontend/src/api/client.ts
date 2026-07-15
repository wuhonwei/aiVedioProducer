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
  force_enrich?: boolean;
  created_at?: string | null;
};

export type StartJobOptions = {
  resumeFromStep?: string | null;
  forceEnrich?: boolean;
  forceShots?: boolean;
};

export type DeepseekHealth = {
  ok: boolean;
  configured: boolean;
  base_url: string;
  model: string;
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

async function readErrorMessage(r: Response): Promise<string> {
  const text = await r.text();
  try {
    const body = JSON.parse(text) as { message?: string; detail?: string };
    if (typeof body.message === "string" && body.message) return body.message;
    if (typeof body.detail === "string" && body.detail) return body.detail;
  } catch {
    // keep raw text
  }
  return text || `${r.status} ${r.statusText}`;
}

async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, init);
  if (!r.ok) throw new Error(await readErrorMessage(r));
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

export const startJob = (projectId: string, options?: StartJobOptions | string | null) => {
  const opts: StartJobOptions =
    typeof options === "string" || options == null
      ? { resumeFromStep: options }
      : options;
  const body: Record<string, unknown> = {};
  if (opts.resumeFromStep != null) body.resume_from_step = opts.resumeFromStep;
  if (opts.forceEnrich) body.force_enrich = true;
  if (opts.forceShots) body.force_shots = true;
  return req<Job>(`/api/projects/${projectId}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
};

export const getJob = (projectId: string, jobId: string) =>
  req<Job>(`/api/projects/${projectId}/jobs/${jobId}`);

export const getLatestJob = (projectId: string) =>
  req<Job>(`/api/projects/${projectId}/jobs/latest`);

export const cancelJob = (projectId: string, jobId: string) =>
  req<Job>(`/api/projects/${projectId}/jobs/${jobId}/cancel`, {
    method: "POST",
  });

export const getBible = (projectId: string) =>
  req<Record<string, unknown>>(`/api/projects/${projectId}/bible`);

export type BibleBlockMeta = {
  block: string;
  review_status: string;
  locked?: boolean;
  notes?: Array<{ note?: string }>;
  source_refs?: unknown[];
};

export type BibleMeta = {
  schema_version?: number;
  blocks: Record<string, BibleBlockMeta>;
  reviews?: unknown[];
};

export const getBibleMeta = (projectId: string) =>
  req<BibleMeta>(`/api/projects/${projectId}/bible/meta`);

export const reviewBibleBlock = (
  projectId: string,
  body: { block: string; action: string; note?: string },
) =>
  req<BibleMeta>(`/api/projects/${projectId}/bible/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const lockBibleBlock = (
  projectId: string,
  body: { block: string; locked: boolean },
) =>
  req<BibleMeta>(`/api/projects/${projectId}/bible/lock`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const patchBible = (projectId: string, patch: Record<string, unknown>) =>
  req<Record<string, unknown>>(`/api/projects/${projectId}/bible`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });

export const createExport = (projectId: string) =>
  req<ExportResult>(`/api/projects/${projectId}/exports`, { method: "POST" });

export const healthOllama = () => req<OllamaHealth>("/api/health/ollama");

export const healthDeepseek = () => req<DeepseekHealth>("/api/health/deepseek");

export const getShots = (projectId: string) =>
  req<{
    shots?: Array<Record<string, unknown>>;
    shot_count?: number;
    model?: string;
    warnings?: string[];
    schema_version?: number;
  }>(`/api/projects/${projectId}/shots`);

export const patchShot = (
  projectId: string,
  shotId: string,
  patch: Record<string, unknown>,
) =>
  req<Record<string, unknown>>(`/api/projects/${projectId}/shots/${shotId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });

export const reviewShot = (
  projectId: string,
  shotId: string,
  body: { status: string; note?: string },
) =>
  req<Record<string, unknown>>(`/api/projects/${projectId}/shots/${shotId}/review`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const exportShotsYaml = (projectId: string) =>
  req<{ count: number; root: string }>(`/api/projects/${projectId}/shots/export-yaml`, {
    method: "POST",
  });

export const getAssetPlan = (projectId: string) =>
  req<{
    characters?: Array<Record<string, unknown>>;
    locations?: Array<Record<string, unknown>>;
    props?: Array<Record<string, unknown>>;
  }>(`/api/projects/${projectId}/assets/plan`);

export const regenerateAssetPlan = (projectId: string, approvedOnly = false) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/assets/plan/regenerate?approved_only=${approvedOnly}`,
    { method: "POST" },
  );

export type VisualCharacter = {
  character_id: string;
  name: string;
  trigger: string;
  candidate_count: number;
  curated_count: number;
  lora_ready: boolean;
  candidates: string[];
  curated: string[];
  status?: string;
  prompt_zh?: string;
};

export const listVisualCharacters = (projectId: string) =>
  req<{ characters: VisualCharacter[]; backend: string }>(
    `/api/projects/${projectId}/visual/characters`,
  );

export const startVisualCandidates = (
  projectId: string,
  body?: { character_ids?: string[]; count?: number },
) =>
  req<{ id: string; status: string }>(`/api/projects/${projectId}/visual/candidates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });

export const getVisualJob = (projectId: string, jobId: string) =>
  req<{
    id: string;
    status: string;
    progress_done?: number;
    progress_total?: number;
    error?: string | null;
    result?: unknown;
  }>(`/api/projects/${projectId}/visual/jobs/${jobId}`);

export const curateVisualCharacter = (
  projectId: string,
  characterId: string,
  keep: string[],
) =>
  req<{ curated: string[]; count: number }>(
    `/api/projects/${projectId}/visual/characters/${characterId}/curate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keep }),
    },
  );

export const trainVisualLora = (projectId: string, characterIds?: string[]) =>
  req<{ results: Array<Record<string, unknown>> }>(
    `/api/projects/${projectId}/visual/lora/train`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character_ids: characterIds }),
    },
  );

export const visualT2I = (
  projectId: string,
  body: { character_id: string; prompt: string; shot_id?: string },
) =>
  req<Record<string, unknown>>(`/api/projects/${projectId}/visual/t2i`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const visualFileUrl = (
  projectId: string,
  characterId: string,
  folder: string,
  filename: string,
) =>
  `/api/projects/${projectId}/visual/characters/${characterId}/files/${folder}/${filename}`;
