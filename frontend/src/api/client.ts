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
  volumes_done?: number;
  volumes_total?: number;
  error_message?: string | null;
  resume_from_step?: string | null;
  force_enrich?: boolean;
  created_at?: string | null;
};

export type StartJobOptions = {
  resumeFromStep?: string | null;
  forceEnrich?: boolean;
  forceShots?: boolean;
  volumeId?: string | null;
  chapterFrom?: string | null;
  chapterTo?: string | null;
};

export const getPipelineReport = (projectId: string, reportName: string) =>
  req<Record<string, unknown> | unknown[]>(
    `/api/projects/${projectId}/reports/${reportName}`,
  );

export const listPipelineReports = (projectId: string) =>
  req<{ reports: Array<{ name: string; available: boolean; path: string }> }>(
    `/api/projects/${projectId}/reports`,
  );

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
  const r = await fetch(`${BASE}${path}`, {
    cache: "no-store",
    ...init,
  });
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
  if (opts.volumeId) body.volume_id = opts.volumeId;
  if (opts.chapterFrom) body.chapter_from = opts.chapterFrom;
  if (opts.chapterTo) body.chapter_to = opts.chapterTo;
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

export const getBible = (projectId: string, sections?: string[]) => {
  const q =
    sections && sections.length
      ? `?sections=${encodeURIComponent(sections.join(","))}`
      : "";
  return req<Record<string, unknown>>(`/api/projects/${projectId}/bible${q}`);
};

export type TimelinePage = {
  items: Array<Record<string, unknown>>;
  offset: number;
  limit: number;
  total_count: number;
  has_more: boolean;
};

export const getTimeline = (projectId: string, offset = 0, limit = 50) =>
  req<TimelinePage>(
    `/api/projects/${projectId}/timeline?offset=${offset}&limit=${limit}`,
  );

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

export const getShots = (
  projectId: string,
  options?: {
    offset?: number;
    limit?: number;
    eventId?: string;
    chapterId?: string;
    reviewStatus?: string;
  },
) => {
  const params = new URLSearchParams();
  if (options?.offset != null) params.set("offset", String(options.offset));
  if (options?.limit != null) params.set("limit", String(options.limit));
  if (options?.eventId) params.set("event_id", options.eventId);
  if (options?.chapterId) params.set("chapter_id", options.chapterId);
  if (options?.reviewStatus) params.set("review_status", options.reviewStatus);
  const q = params.toString() ? `?${params}` : "";
  return req<{
    shots?: Array<Record<string, unknown>>;
    items?: Array<Record<string, unknown>>;
    shot_count?: number;
    total_count?: number;
    offset?: number;
    limit?: number;
    has_more?: boolean;
    model?: string;
    warnings?: string[];
    schema_version?: number;
  }>(`/api/projects/${projectId}/shots${q}`);
};

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

export const exportShotsYaml = (projectId: string, approvedOnly = false) =>
  req<{ count: number; root: string; approved_only?: boolean }>(
    `/api/projects/${projectId}/shots/export-yaml?approved_only=${approvedOnly}`,
    {
      method: "POST",
    },
  );

export const getAssetPlan = (projectId: string) =>
  req<{
    schema_version?: number;
    generated_from?: Record<string, unknown>;
    characters?: Array<Record<string, unknown>>;
    locations?: Array<Record<string, unknown>>;
    props?: Array<Record<string, unknown>>;
  }>(`/api/projects/${projectId}/assets/plan`);

export const regenerateAssetPlan = (projectId: string, approvedOnly = true) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/assets/plan/regenerate?approved_only=${approvedOnly}`,
    { method: "POST" },
  );

export const patchAssetPlanEntry = (
  projectId: string,
  assetType: string,
  assetId: string,
  patch: Record<string, unknown>,
) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/assets/plan/${assetType}/${encodeURIComponent(assetId)}`,
    {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(patch),
    },
  );

export type ExpressionDim = {
  id: string;
  label: string;
  emotion?: string;
  framing?: string;
  status?: string;
  priority?: number;
  evidence?: Array<{ text?: string; source?: string; ref?: string }>;
};

export type VisualCharacter = {
  character_id: string;
  name: string;
  trigger: string;
  candidate_count: number;
  curated_count: number;
  sheet_count?: number;
  generation_count?: number;
  lora_ready: boolean;
  train_status?: string;
  probe_status?: string;
  bootstrap_status?: string;
  bootstrap_warnings?: string[];
  look_lock?: {
    folder?: string;
    file?: string;
    ref_file?: string;
    denoise?: number;
    set_at?: string;
  } | null;
  look_lock_ready?: boolean;
  look_lock_archive?: string[];
  candidates: string[];
  curated: string[];
  sheets?: string[];
  generations?: string[];
  status?: string;
  prompt_zh?: string;
  lora_file?: string | null;
  expression_dims?: ExpressionDim[];
  default_expression?: string;
};

export const listVisualCharacters = (projectId: string) =>
  req<{
    characters: VisualCharacter[];
    backend: string;
    lora_train_configured?: boolean;
  }>(`/api/projects/${projectId}/visual/characters`);

export const startVisualCandidates = (
  projectId: string,
  body?: { character_ids?: string[]; count?: number },
) =>
  req<{ id: string; status: string }>(`/api/projects/${projectId}/visual/candidates`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });

export const startVisualBootstrap = (
  projectId: string,
  body?: { character_ids?: string[] },
) =>
  req<{ id: string; status: string; kind?: string }>(
    `/api/projects/${projectId}/visual/bootstrap`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    },
  );

export const confirmVisualBootstrap = (projectId: string, characterId: string) =>
  req<{ character_id: string; bootstrap_status: string; train_status: string }>(
    `/api/projects/${projectId}/visual/characters/${characterId}/bootstrap/confirm`,
    { method: "POST" },
  );

export const skipVisualBootstrap = (projectId: string, characterId: string) =>
  req<{ character_id: string; bootstrap_status: string }>(
    `/api/projects/${projectId}/visual/characters/${characterId}/bootstrap/skip`,
    { method: "POST" },
  );

export const swapVisualBootstrapLookLock = (
  projectId: string,
  characterId: string,
  body: { filename: string; folder?: string; denoise?: number },
) =>
  req<{
    character_id: string;
    bootstrap_status: string;
    swapped_from: { folder: string; file: string };
  }>(
    `/api/projects/${projectId}/visual/characters/${characterId}/bootstrap/swap-look-lock`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );

export type VisualLocation = {
  location_id: string;
  name: string;
  trigger: string;
  candidate_count: number;
  curated_count: number;
  sheet_count?: number;
  lora_ready: boolean;
  train_status?: string;
  bootstrap_status?: string;
  bootstrap_warnings?: string[];
  look_lock?: {
    folder?: string;
    file?: string;
    ref_file?: string;
    denoise?: number;
  } | null;
  look_lock_ready?: boolean;
  look_lock_archive?: string[];
  candidates: string[];
  curated: string[];
  sheets?: string[];
  prompt_zh?: string;
  status?: string;
};

export const listVisualLocations = (projectId: string) =>
  req<{
    locations: VisualLocation[];
    backend: string;
    lora_train_configured?: boolean;
  }>(`/api/projects/${projectId}/visual/locations`);

export const startVisualLocationBootstrap = (
  projectId: string,
  body?: { location_ids?: string[] },
) =>
  req<{ id: string; status: string; kind?: string }>(
    `/api/projects/${projectId}/visual/locations/bootstrap`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    },
  );

export const confirmVisualLocationBootstrap = (
  projectId: string,
  locationId: string,
) =>
  req<{ location_id: string; bootstrap_status: string; train_status: string }>(
    `/api/projects/${projectId}/visual/locations/${locationId}/bootstrap/confirm`,
    { method: "POST" },
  );

export const skipVisualLocationBootstrap = (
  projectId: string,
  locationId: string,
) =>
  req<{ location_id: string; bootstrap_status: string }>(
    `/api/projects/${projectId}/visual/locations/${locationId}/bootstrap/skip`,
    { method: "POST" },
  );

export const swapVisualLocationBootstrapLookLock = (
  projectId: string,
  locationId: string,
  body: { filename: string; folder?: string; denoise?: number },
) =>
  req<{
    location_id: string;
    bootstrap_status: string;
    swapped_from: { folder: string; file: string };
  }>(
    `/api/projects/${projectId}/visual/locations/${locationId}/bootstrap/swap-look-lock`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );

export const visualLocationFileUrl = (
  projectId: string,
  locationId: string,
  folder: string,
  filename: string,
) =>
  `/api/projects/${projectId}/visual/locations/${locationId}/files/${folder}/${filename}`;

export const setVisualLookLock = (
  projectId: string,
  characterId: string,
  body: { folder: string; filename: string; denoise?: number },
) =>
  req<{ look_lock: Record<string, unknown> }>(
    `/api/projects/${projectId}/visual/characters/${characterId}/look-lock`,
    {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    },
  );

export const clearVisualLookLock = (projectId: string, characterId: string) =>
  req<{ look_lock: null }>(
    `/api/projects/${projectId}/visual/characters/${characterId}/look-lock`,
    { method: "DELETE" },
  );

export const startVisualSheets = (
  projectId: string,
  characterId: string,
  opts?: { group?: string; slot_keys?: string[] },
) =>
  req<{ id: string; status: string }>(`/api/projects/${projectId}/visual/sheets`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      character_id: characterId,
      group: opts?.group ?? "all",
      slot_keys: opts?.slot_keys,
    }),
  });

export const rebuildExpressionDims = (
  projectId: string,
  characterId?: string,
) =>
  characterId
    ? req<{
        character_id: string;
        expression_dims: ExpressionDim[];
        events_used: number;
      }>(
        `/api/projects/${projectId}/bible/characters/${characterId}/expression-dims/rebuild`,
        { method: "POST" },
      )
    : req<{
        updated: number;
        characters: Array<{
          id: string;
          name: string;
          dim_count: number;
          expression_dims: ExpressionDim[];
        }>;
        events_used: number;
      }>(`/api/projects/${projectId}/bible/expression-dims/rebuild`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({}),
      });

export const getVisualJob = (projectId: string, jobId: string) =>
  req<{
    id: string;
    status: string;
    kind?: string;
    progress_done?: number;
    progress_total?: number;
    progress_note?: string | null;
    current_character_id?: string | null;
    current_location_id?: string | null;
    bootstrap_step?: string | null;
    items?: Array<{
      character_id: string;
      name: string;
      status: string;
      error?: string | null;
      lora_file?: string | null;
    }>;
    skipped?: Array<{
      character_id: string;
      name: string;
      status: string;
      error?: string | null;
    }>;
    error?: string | null;
    result?: unknown;
  }>(`/api/projects/${projectId}/visual/jobs/${jobId}`);


export const curateVisualCharacter = (
  projectId: string,
  characterId: string,
  keep: string[],
  keepSheets?: string[],
) =>
  req<{ curated: string[]; count: number; sources?: Array<{ folder: string; file: string }> }>(
    `/api/projects/${projectId}/visual/characters/${characterId}/curate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ keep, keep_sheets: keepSheets || [] }),
    },
  );

export const checkVisualTrainset = (projectId: string, characterId: string) =>
  req<{
    character_id: string;
    trigger: string;
    image_count: number;
    caption_count: number;
    candidate_count: number;
    turnaround_count: number;
    expression_count: number;
    has_front: boolean;
    has_side: boolean;
    has_back: boolean;
    missing_captions: string[];
    trigger_mismatch: string[];
    warnings: string[];
    can_train: boolean;
    score: number;
  }>(`/api/projects/${projectId}/visual/characters/${characterId}/trainset/check`);

export const packageVisualLora = (projectId: string, characterId: string) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/visual/characters/${characterId}/lora/package`,
    { method: "POST" },
  );

export const packageVisualLoraBatch = (
  projectId: string,
  characterIds?: string[],
) =>
  req<{ results: Array<Record<string, unknown>> }>(
    `/api/projects/${projectId}/visual/lora/package`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character_ids: characterIds }),
    },
  );

export const startVisualLoraTrain = (projectId: string, characterId: string) =>
  req<{ id: string; status: string; kind?: string }>(
    `/api/projects/${projectId}/visual/characters/${characterId}/lora/train`,
    { method: "POST" },
  );

export type BatchTrainItem = {
  character_id: string;
  name: string;
  status: string;
  error?: string | null;
  lora_file?: string | null;
};

export const startVisualLoraTrainBatch = (
  projectId: string,
  body?: { character_ids?: string[]; auto_package?: boolean },
) =>
  req<{
    id: string;
    status: string;
    kind?: string;
    progress_total?: number;
    items?: BatchTrainItem[];
    skipped?: BatchTrainItem[];
  }>(`/api/projects/${projectId}/visual/lora/train/batch`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      character_ids: body?.character_ids,
      auto_package: body?.auto_package ?? true,
    }),
  });

/** @deprecated Prefer packageVisualLora + startVisualLoraTrain */
export const trainVisualLora = (projectId: string, characterIds?: string[]) =>
  req<{ results: Array<Record<string, unknown>> }>(
    `/api/projects/${projectId}/visual/lora/train`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character_ids: characterIds }),
    },
  );

export const probeVisualLora = (
  projectId: string,
  characterId: string,
  prompt = "",
) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/visual/characters/${characterId}/lora/probe`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ character_id: characterId, prompt, is_probe: true }),
    },
  );

export const approveVisualLora = (projectId: string, characterId: string) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/visual/characters/${characterId}/lora/approve`,
    { method: "POST" },
  );

export const rejectVisualLora = (
  projectId: string,
  characterId: string,
  note = "",
) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/visual/characters/${characterId}/lora/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ note }),
    },
  );

export const visualT2I = (
  projectId: string,
  body: {
    character_id?: string;
    character_ids?: string[];
    location_id?: string;
    prompt: string;
    shot_id?: string;
    is_probe?: boolean;
    use_location_lora?: boolean;
  },
) =>
  req<Record<string, unknown>>(`/api/projects/${projectId}/visual/t2i`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

export const deleteVisualFile = (
  projectId: string,
  characterId: string,
  folder: string,
  filename: string,
) =>
  req<{ deleted: boolean }>(
    `/api/projects/${projectId}/visual/characters/${characterId}/files/${folder}/${filename}`,
    { method: "DELETE" },
  );

export const visualFileUrl = (
  projectId: string,
  characterId: string,
  folder: string,
  filename: string,
) =>
  `/api/projects/${projectId}/visual/characters/${characterId}/files/${folder}/${filename}`;

export const generateKeyframes = (
  projectId: string,
  shotId: string,
  body?: {
    count?: number;
    use_location_lora?: boolean;
    force?: boolean;
    prompt_override?: string;
    negative_override?: string;
  },
) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/keyframes/${encodeURIComponent(shotId)}/generate`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        count: body?.count ?? 4,
        use_location_lora: body?.use_location_lora ?? false,
        force: body?.force ?? false,
        prompt_override: body?.prompt_override ?? "",
        negative_override: body?.negative_override ?? "",
      }),
    },
  );

export const getKeyframes = (projectId: string, shotId: string) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/keyframes/${encodeURIComponent(shotId)}`,
  );

export const selectKeyframe = (
  projectId: string,
  shotId: string,
  filename: string,
  note = "",
) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/keyframes/${encodeURIComponent(shotId)}/select`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, note }),
    },
  );

export const rejectKeyframe = (
  projectId: string,
  shotId: string,
  filename: string,
  reason = "",
) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/keyframes/${encodeURIComponent(shotId)}/reject`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filename, reason }),
    },
  );

export const deleteKeyframeCandidate = (
  projectId: string,
  shotId: string,
  filename: string,
) =>
  req<Record<string, unknown>>(
    `/api/projects/${projectId}/keyframes/${encodeURIComponent(shotId)}/candidates/${encodeURIComponent(filename)}`,
    { method: "DELETE" },
  );

export const keyframeFileUrl = (
  projectId: string,
  shotId: string,
  filename: string,
) =>
  `/api/projects/${projectId}/keyframes/${encodeURIComponent(shotId)}/files/${encodeURIComponent(filename)}`;
