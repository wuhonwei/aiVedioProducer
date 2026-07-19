# Keyframe Module (Phase 1)

**Date:** 2026-07-19  
**Status:** Implemented  
**Baseline:** `0bb6709`  
**Depends on:** `2026-07-19-optional-location-lora-shot-t2i-design.md`, character/location LoRA visual stack  
**Roadmap:** Sub-project 1 of the 2026-07-19 next-stage TODO (C). Later phases (LoRA recovery, VisualPage split, LoRA weight policy, QA tags, train templates, I2V, timeline) are **out of scope** here.

## Goal

Turn today’s ephemeral ShotsPage「生成镜头图」preview into a **shot-centric Keyframe asset**:

```text
approved shot
  → generate N keyframe candidates
  → human selects one
  → selected.json (keyframe_ready)
```

This is the bridge to a future I2V module.

## Non-goals (this phase)

- I2V / video candidates / FFmpeg timeline.
- VisualPage.tsx split.
- LoRA train logs / retry / reset / package stale detection.
- Full multi-LoRA weight policy UI (only a hard cap of 3 LoRAs + warnings).
- Vision auto-QA for keyframes (manual select/reject only).
- Deleting or migrating historical `visual/.../generations/shot_*.png` files.
- Persisting `use_location_lora` on the shot document.

## Decisions

| Topic | Choice |
|-------|--------|
| Approach | **Thin wrapper** around `generate_shot_with_loras` (copy/move result into keyframes tree) |
| Storage root | `{data_root}/projects/{project_id}/keyframes/{shot_id}/` |
| Default `use_location_lora` | `false` |
| Missing character LoRA | **Warning**, still generate (text + any ready LoRAs) |
| Max LoRAs stacked | **3** (location first if enabled, then characters in cast order); overflow → warning |
| Generation mode | **Synchronous** API (count default 4); no new job queue in v1 |
| Old ShotsPage preview button | **Replace** with Keyframe panel actions (no duplicate ephemeral preview path) |
| Shot document flag | Write `generation.keyframe_status` / `generation.keyframe_selected` on the shot when selecting (best-effort via existing shot patch helpers); **source of truth** remains `keyframes/{shot_id}/selected.json` |

## Directory layout

```text
data/projects/{project_id}/keyframes/
  {shot_id}/
    candidates/
      kf_0001.png
      kf_0001.json
      kf_0002.png
      kf_0002.json
    selected.json
    generation.json
    review.json
```

### `generation.json`

Last generate request summary:

```json
{
  "shot_id": "shot_000001",
  "prompt": "...",
  "negative": "...",
  "character_ids": ["ent_0001"],
  "location_id": "loc_xxx",
  "use_location_lora": false,
  "loras": [
    {
      "type": "character",
      "id": "ent_0001",
      "file": "xxx_aivp.safetensors",
      "trigger": "xxx_aivp",
      "weight": 0.75
    }
  ],
  "backend": "comfy",
  "created_at": "2026-07-19T00:00:00+00:00",
  "candidate_count": 4,
  "warnings": []
}
```

### `candidates/kf_NNNN.json`

```json
{
  "file": "kf_0001.png",
  "shot_id": "shot_000001",
  "seed": 123,
  "prompt": "...",
  "negative": "...",
  "loras": [],
  "created_at": "2026-07-19T00:00:00+00:00",
  "quality": {
    "status": "unchecked",
    "warnings": []
  }
}
```

Filenames are zero-padded sequential within the shot folder (`kf_0001`, `kf_0002`, …), continuing after existing max index when regenerating (unless `force=true` clears candidates first).

### `selected.json`

```json
{
  "shot_id": "shot_000001",
  "selected_file": "kf_0002.png",
  "selected_at": "2026-07-19T00:00:00+00:00",
  "review_status": "approved",
  "note": "角色一致性最好"
}
```

### `review.json`

Append-only list of reject / note events:

```json
{
  "events": [
    {
      "at": "...",
      "action": "reject",
      "filename": "kf_0001.png",
      "reason": "角色脸不一致"
    }
  ]
}
```

## Backend modules

```text
backend/src/aivp/keyframes/__init__.py
backend/src/aivp/keyframes/paths.py      # KeyframePaths
backend/src/aivp/keyframes/store.py      # read/write selected, list candidates, delete
backend/src/aivp/keyframes/generate.py   # resolve shot → generate_shot_with_loras × N → store
backend/src/aivp/api/routes_keyframes.py
```

Register in `app.py`: `app.include_router(keyframes_router, prefix="/api")`.

### `KeyframePaths`

Mirror `VisualPaths` style:

- `root` = `projects/{id}/keyframes`
- `shot_dir(shot_id)`, `candidates_dir(shot_id)`
- `generation_json`, `selected_json`, `review_json`
- `ensure_shot(shot_id)`

Validate `shot_id` / filenames: no path separators, no `..`, `.png` only for deletes.

### Generate flow (`generate.py`)

1. Load `shot_script.json` via existing shot load helpers (`ProjectPaths` + upgrade if needed).
2. Find shot by `shot_id`; 404 if missing.
3. Resolve `character_ids` / `location_id` from `asset_refs` (prefer ids), fallback to cast / location names via asset plan name maps (same spirit as ShotsPage).
4. Build prompt: `prompt_override` or shot `visual_prompt` (required non-empty after strip → 400).
5. Negative: `negative_override` or shot `negative_prompt` or a short default.
6. Cap LoRA stack at 3 inside a thin pre-pass or by trimming ids passed to `generate_shot_with_loras` + collect warnings (`too_many_loras`, `character_lora_not_ready`, `location_lora_disabled_by_default` / `location_lora_not_ready`).
7. For `i in 1..count`:
   - Call `generate_shot_with_loras(..., use_location_lora=..., settings=...)`.
   - Copy/move PNG into `candidates/kf_XXXX.png`.
   - Write sidecar JSON (seed/prompt/loras from generate return + meta next to image if present).
8. Write `generation.json`.
9. If `force=true`, delete previous candidates + clear `selected.json` before generating.

`count` default **4**, clamp **1..8**.

Reuse `get_image_backend(settings)` — stub in tests, comfy in production.

### Select / reject / delete

- **select:** filename must exist under candidates; write `selected.json` with `review_status=approved`; update shot `generation.keyframe_status=selected` + `keyframe_file` best-effort.
- **reject:** append `review.json` event; if rejected file is currently selected, clear selection / set status `rejected`; set candidate meta `quality.status=rejected` when sidecar exists.
- **delete candidate:** remove png+json; if it was selected, clear selection.

## API

Base: `/api/projects/{project_id}/keyframes/{shot_id}`

| Method | Path | Body | Notes |
|--------|------|------|-------|
| POST | `/generate` | `{ count?, use_location_lora?, force?, prompt_override?, negative_override? }` | Sync; returns candidates + warnings |
| GET | `/` | — | selected + candidates + generation + derived status |
| POST | `/select` | `{ filename, note? }` | |
| POST | `/reject` | `{ filename, reason? }` | |
| DELETE | `/candidates/{filename}` | — | |
| GET | `/files/{filename}` | — | Serve png from candidates (or selected file) |

Auth / project checks: same `_require_project` pattern as `routes_visual`.

### GET status field

Derived:

| Condition | `status` |
|-----------|----------|
| no candidates | `empty` |
| candidates, no selected | `candidates` |
| selected.json present | `selected` |
| last review reject cleared selection | `rejected` |

## Frontend

### Client (`frontend/src/api/client.ts`)

Add:

- `generateKeyframes(projectId, shotId, body)`
- `getKeyframes(projectId, shotId)`
- `selectKeyframe(...)`
- `rejectKeyframe(...)`
- `deleteKeyframeCandidate(...)`
- `keyframeFileUrl(projectId, shotId, filename)`

### ShotsPage

On selected shot detail, replace ephemeral「生成镜头图」block with **Keyframe panel**:

- Status chip: 未生成 / 已生成候选 / 已选择 / 已退回
- Checkbox 使用地点 LoRA (default off; disable when no location or not `lora_ready`)
- Button 生成关键帧候选 (`count=4`)
- Optional note: LoRA ready summary from GET warnings / generation.loras
- Candidate grid with lightbox (inline minimal lightbox OK; no VisualPage split yet)
- 设为选中 / 退回 / 删除

Race guards: keep existing `selectedIdRef` / token pattern so switching shots mid-generate does not paint wrong shot.

## Testing

| Test | Assert |
|------|--------|
| `test_keyframe_paths` | dirs created under project |
| `test_keyframe_store_select_reject` | selected.json / review.json |
| `test_generate_keyframes_stub` | StubImageBackend → N candidates + generation.json |
| `test_keyframes_api` | TestClient generate → get → select |
| `test_lora_cap_warning` | >3 ready characters → warning + ≤3 stacked |

## Acceptance (MVP)

1. User opens ShotsPage, selects a shot with `asset_refs`.
2. Clicks「生成关键帧」→ 1–4 candidates under `keyframes/{shot_id}/candidates/`.
3. Each candidate has meta json.
4. GET returns candidates; select writes `selected.json`.
5. Location LoRA remains opt-in default off.
6. Unit/API tests pass with stub backend.

## Follow-ups (explicitly deferred)

2. LoRA logs / retry / reset  
3. VisualPage split  
4. Rich LoRA weight policy  
5. Keyframe quality tags UI  
6. Train templates  
7. I2V from `selected.json`  
8. Timeline / audio fields  

## Spec self-review

- No TBD placeholders.
- Sync generate + thin wrapper matches approved approach A.
- Source of truth for selection is `selected.json`; shot document update is best-effort only.
- Scope limited to Phase 1; roadmap C continues as separate specs/plans.
