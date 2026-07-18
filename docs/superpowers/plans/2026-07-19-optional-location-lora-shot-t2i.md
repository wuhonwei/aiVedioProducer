# Optional Location LoRA on Shot T2I Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make location LoRA opt-in (default off) for shot keyframe generation, and expose it on ShotsPage via「生成镜头图」+「使用地点 LoRA」.

**Architecture:** Gate location LoRA stacking in `generate_shot_with_loras` with `use_location_lora: bool = False` while still injecting location text into the prompt. Route shot keyframes through extended `POST /visual/t2i`; keep character probe on `generate_with_character`. ShotsPage calls the API with a checkbox defaulting unchecked.

**Tech Stack:** FastAPI, Pydantic, pytest, React + TypeScript (existing Visual/Shots client helpers).

**Spec:** `docs/superpowers/specs/2026-07-19-optional-location-lora-shot-t2i-design.md`

## Global Constraints

- `use_location_lora` defaults to **false** everywhere (API body, function kwarg, UI checkbox).
- When flag is false: do **not** stack location LoRA; still inject location trigger / `prompt_zh` if `location_id` set.
- Do not persist the flag on the shot document.
- Do not change location bootstrap / train flows.
- VisualPage character probe t2i must keep working with existing `{ character_id, prompt, is_probe }` bodies.
- Prefer stub image backend in tests; no Comfy required.

## File map

| File | Role |
|------|------|
| `backend/src/aivp/visual/t2i.py` | Add `use_location_lora`; gate LoRA stack; return flag |
| `backend/tests/test_location_t2i_stack.py` | On/off + default-off tests |
| `backend/src/aivp/api/routes_visual.py` | Extend `T2IBody`; route shot vs probe in `t2i` |
| `frontend/src/api/client.ts` | Extend `visualT2I` body type |
| `frontend/src/pages/ShotsPage.tsx` | Generate button + checkbox + preview |

---

### Task 1: Gate location LoRA in `generate_shot_with_loras`

**Files:**
- Modify: `backend/src/aivp/visual/t2i.py` (`generate_shot_with_loras`)
- Test: `backend/tests/test_location_t2i_stack.py`

**Interfaces:**
- Consumes: existing `generate_shot_with_loras`, `StubImageBackend`, location/character profile helpers
- Produces: `generate_shot_with_loras(..., use_location_lora: bool = False) -> dict` including key `use_location_lora: bool`; when false, `loras` has no location entry and `location_lora_file` is `None`

- [ ] **Step 1: Write the failing tests**

Append to `backend/tests/test_location_t2i_stack.py`:

```python
def test_generate_shot_skips_location_lora_by_default(tmp_path: Path):
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    loc = {"id": "loc_1", "name": "渡口", "tier": "major", "prompt_zh": "青石渡口"}
    loc_p = ensure_location_profile(v, loc)
    loc_p["lora_ready"] = True
    loc_p["lora_file"] = "dukou_loc.safetensors"
    loc_p["trigger"] = "dukou_loc_aivp"
    save_location_profile(v, loc_p)
    (v.location_lora_dir("loc_1") / "dukou_loc.safetensors").write_bytes(b"lora")

    ch = {
        "id": "ent_1",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "青灰布衣少年",
        "gender_presentation": "masculine",
    }
    cp = ensure_profile(v, ch)
    cp["lora_ready"] = True
    cp["lora_file"] = "lin_aivp.safetensors"
    save_profile(v, cp)
    (v.lora_dir("ent_1") / "lin_aivp.safetensors").write_bytes(b"lora")

    out = generate_shot_with_loras(
        v,
        StubImageBackend(),
        prompt="立于埠头",
        location_id="loc_1",
        character_ids=["ent_1"],
        shot_id="s1",
    )
    assert out.get("use_location_lora") is False
    assert out["location_lora_file"] is None
    assert len(out["loras"]) == 1
    assert out["loras"][0]["name"] == "lin_aivp.safetensors"
    assert "dukou_loc_aivp" in out["prompt"] or "青石渡口" in out["prompt"]


def test_generate_shot_stacks_location_lora_when_enabled(tmp_path: Path):
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    loc = {"id": "loc_1", "name": "渡口", "tier": "major", "prompt_zh": "青石渡口"}
    loc_p = ensure_location_profile(v, loc)
    loc_p["lora_ready"] = True
    loc_p["lora_file"] = "dukou_loc.safetensors"
    save_location_profile(v, loc_p)
    (v.location_lora_dir("loc_1") / "dukou_loc.safetensors").write_bytes(b"lora")

    ch = {
        "id": "ent_1",
        "name": "林砚之",
        "tier": "major",
        "prompt_zh": "青灰布衣少年",
        "gender_presentation": "masculine",
    }
    cp = ensure_profile(v, ch)
    cp["lora_ready"] = True
    cp["lora_file"] = "lin_aivp.safetensors"
    save_profile(v, cp)
    (v.lora_dir("ent_1") / "lin_aivp.safetensors").write_bytes(b"lora")

    out = generate_shot_with_loras(
        v,
        StubImageBackend(),
        prompt="立于埠头",
        location_id="loc_1",
        character_ids=["ent_1"],
        shot_id="s1",
        use_location_lora=True,
    )
    assert out.get("use_location_lora") is True
    assert len(out["loras"]) == 2
    assert out["loras"][0]["name"] == "dukou_loc.safetensors"
    assert out["loras"][1]["name"] == "lin_aivp.safetensors"
    assert out["location_lora_file"] == "dukou_loc.safetensors"
```

Also update existing `test_generate_shot_with_loras_records_stack` to pass `use_location_lora=True` so it still expects 2 LoRAs.

- [ ] **Step 2: Run tests to verify they fail**

Run:

```bash
cd backend
python -m pytest tests/test_location_t2i_stack.py::test_generate_shot_skips_location_lora_by_default tests/test_location_t2i_stack.py::test_generate_shot_stacks_location_lora_when_enabled -v
```

Expected: FAIL (unexpected LoRA count / missing `use_location_lora`, or TypeError on unknown kwarg).

- [ ] **Step 3: Implement minimal gate**

In `backend/src/aivp/visual/t2i.py`, change `generate_shot_with_loras` signature and location LoRA block:

```python
def generate_shot_with_loras(
    vpaths: VisualPaths,
    backend: ImageBackend,
    *,
    prompt: str,
    location_id: str | None = None,
    character_ids: list[str] | None = None,
    negative: str | None = None,
    shot_id: str | None = None,
    location_strength: float | None = None,
    use_location_lora: bool = False,
) -> dict[str, Any]:
    """Txt2img with optional location LoRA first, then character LoRAs stacked."""
    loras: list[dict[str, Any]] = []
    prompt_bits: list[str] = []
    loc_trigger = ""
    loc_file = None
    if location_id:
        loc_profile = read_location_profile(vpaths.location_profile_json(location_id)) or {}
        loc_trigger = str(loc_profile.get("trigger") or "")
        loc_look = str(loc_profile.get("prompt_zh") or "").strip()
        if loc_trigger:
            prompt_bits.append(loc_trigger)
        if loc_look:
            prompt_bits.append(loc_look)
        if use_location_lora and loc_profile.get("lora_ready"):
            loc_file = _location_lora_basename(loc_profile, vpaths, location_id)
            if loc_file:
                strength = float(
                    location_strength
                    if location_strength is not None
                    else loc_profile.get("lora_weight_default")
                    or DEFAULT_LOCATION_LORA_WEIGHT
                )
                loras.append({"name": loc_file, "strength": strength})
    # ... character loop unchanged ...
```

In the return dict add:

```python
"use_location_lora": bool(use_location_lora),
"location_lora_file": loc_file,
```

(`location_lora_file` stays `None` when flag is false even if a file exists on disk.)

- [ ] **Step 4: Run tests to verify they pass**

Run:

```bash
cd backend
python -m pytest tests/test_location_t2i_stack.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit** (only if user asked to commit in this session)

```bash
git add backend/src/aivp/visual/t2i.py backend/tests/test_location_t2i_stack.py
git commit -m "fix(visual): default location LoRA off for shot t2i"
```

---

### Task 2: Extend `/visual/t2i` for shot keyframes

**Files:**
- Modify: `backend/src/aivp/api/routes_visual.py` (`T2IBody`, `t2i`)
- Test: `backend/tests/test_visual_t2i_shot_route.py` (create)

**Interfaces:**
- Consumes: `generate_shot_with_loras(..., use_location_lora=...)`, `generate_with_character`
- Produces: `T2IBody` fields below; `t2i` routes per spec

`T2IBody` fields:

| Field | Type | Default |
|-------|------|---------|
| `character_id` | `str \| None` | `None` |
| `character_ids` | `list[str]` | `[]` |
| `location_id` | `str \| None` | `None` |
| `prompt` | `str` | `""` |
| `shot_id` | `str \| None` | `None` |
| `is_probe` | `bool` | `False` |
| `use_location_lora` | `bool` | `False` |

Routing:

- If `is_probe` **or** (`not location_id` and not `character_ids`): require `character_id`, call `generate_with_character`.
- Else: build `ids = character_ids or ([character_id] if character_id else [])`, call `generate_shot_with_loras(..., use_location_lora=body.use_location_lora)`.

- [ ] **Step 1: Write the failing API tests**

Create `backend/tests/test_visual_t2i_shot_route.py` using the project’s existing FastAPI test client pattern. If no shared fixture exists, mirror the lightest nearby visual route test (search `TestClient` / `app` in `backend/tests`).

Minimal assertions (adapt fixture names to repo):

```python
def test_t2i_shot_defaults_location_lora_off(client, project_id, seeded_loc_and_char):
    r = client.post(
        f"/api/projects/{project_id}/visual/t2i",
        json={
            "location_id": "loc_1",
            "character_ids": ["ent_1"],
            "prompt": "远望江雾",
            "shot_id": "s1",
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["use_location_lora"] is False
    assert all(x["name"] != "dukou_loc.safetensors" for x in data.get("loras") or [])


def test_t2i_shot_can_enable_location_lora(client, project_id, seeded_loc_and_char):
    r = client.post(
        f"/api/projects/{project_id}/visual/t2i",
        json={
            "location_id": "loc_1",
            "character_ids": ["ent_1"],
            "prompt": "远望江雾",
            "shot_id": "s1",
            "use_location_lora": True,
        },
    )
    assert r.status_code == 200
    data = r.json()
    assert data["use_location_lora"] is True
    assert data["loras"][0]["name"] == "dukou_loc.safetensors"


def test_t2i_probe_still_uses_character_path(client, project_id, seeded_char):
    r = client.post(
        f"/api/projects/{project_id}/visual/t2i",
        json={"character_id": "ent_1", "prompt": "站立", "is_probe": True},
    )
    assert r.status_code == 200
    # probe path should not require location fields; response matches generate_with_character shape
    assert "file" in r.json() or "path" in r.json()
```

If full HTTP fixtures are heavy, unit-test the routing helper extracted as `_resolve_t2i_call(body) -> ("character"|"shot", kwargs)` instead — prefer HTTP if a client fixture already exists.

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd backend
python -m pytest tests/test_visual_t2i_shot_route.py -v
```

Expected: FAIL (validation error on extra fields / always character path).

- [ ] **Step 3: Implement body + routing**

Replace `T2IBody` and `t2i` in `routes_visual.py`:

```python
class T2IBody(BaseModel):
    character_id: str | None = None
    character_ids: list[str] = []
    location_id: str | None = None
    prompt: str = ""
    shot_id: str | None = None
    is_probe: bool = False
    use_location_lora: bool = False


@router.post("/projects/{project_id}/visual/t2i")
def t2i(
    project_id: str,
    body: T2IBody,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    _require_project(db, project_id)
    vpaths = VisualPaths(settings.data_root, project_id)
    backend = get_image_backend(settings)
    char_ids = list(body.character_ids or [])
    if not char_ids and body.character_id:
        char_ids = [body.character_id]
    use_shot_stack = (not body.is_probe) and (
        bool(body.location_id) or bool(body.character_ids)
    )
    if use_shot_stack:
        from aivp.visual.t2i import generate_shot_with_loras

        try:
            return generate_shot_with_loras(
                vpaths,
                backend,
                prompt=body.prompt,
                location_id=body.location_id,
                character_ids=char_ids or None,
                shot_id=body.shot_id,
                use_location_lora=bool(body.use_location_lora),
            )
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
    if not body.character_id:
        raise HTTPException(status_code=400, detail="character_id_required")
    return generate_with_character(
        vpaths,
        body.character_id,
        body.prompt,
        backend,
        shot_id=body.shot_id,
        is_probe=bool(body.is_probe),
    )
```

Update import at top if `generate_shot_with_loras` should be imported statically with `generate_with_character`.

Note: `probe_lora` still passes `T2IBody | None` and uses path `character_id` — unchanged.

- [ ] **Step 4: Run tests**

```bash
cd backend
python -m pytest tests/test_visual_t2i_shot_route.py tests/test_location_t2i_stack.py -v
```

Expected: PASS.

- [ ] **Step 5: Commit** (only if user asked)

```bash
git add backend/src/aivp/api/routes_visual.py backend/tests/test_visual_t2i_shot_route.py
git commit -m "feat(api): optional use_location_lora on visual t2i"
```

---

### Task 3: ShotsPage generate UI + client types

**Files:**
- Modify: `frontend/src/api/client.ts` (`visualT2I`)
- Modify: `frontend/src/pages/ShotsPage.tsx`

**Interfaces:**
- Consumes: `visualT2I`, `listVisualLocations`, `visualFileUrl`, `visualLocationFileUrl`
- Produces: UI calling t2i with `use_location_lora` default false

- [ ] **Step 1: Extend client type**

In `frontend/src/api/client.ts`:

```typescript
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
```

- [ ] **Step 2: Add ShotsPage controls**

In `ShotsPage.tsx`:

1. Import `visualT2I`, `listVisualLocations`, `visualFileUrl`, `visualLocationFileUrl`, type `VisualLocation`.
2. State:
   - `useLocationLora` default `false`
   - `genBusy` boolean
   - `genPreviewUrl` string | null
   - `locations` from `listVisualLocations` (load with shots or on mount) for `lora_ready` helper
3. Below visual_prompt / near save actions, add:

```tsx
<label className="row" style={{ gap: 8, alignItems: "center" }}>
  <input
    type="checkbox"
    aria-label="use-location-lora"
    checked={useLocationLora}
    disabled={
      !selected.location_id ||
      !locations.find((l) => l.location_id === selected.location_id)?.lora_ready
    }
    onChange={(e) => setUseLocationLora(e.target.checked)}
  />
  使用地点 LoRA
</label>
{selected.location_id &&
  !locations.find((l) => l.location_id === selected.location_id)?.lora_ready && (
    <p className="note">该地点尚未 lora_ready，无法启用地点 LoRA</p>
  )}
<button
  type="button"
  className="btn btn-primary"
  disabled={genBusy || !(selected.cast || selected.characters || []).length && !selected.location_id}
  onClick={() => void onGenerateShot()}
>
  {genBusy ? "生成中…" : "生成镜头图"}
</button>
{genPreviewUrl && (
  <img src={genPreviewUrl} alt="shot preview" style={{ maxWidth: 320, marginTop: 8 }} />
)}
```

4. `onGenerateShot`:

```typescript
const cast = (selected.cast || selected.characters || []).filter(Boolean);
const out = await visualT2I(projectId, {
  shot_id: selected.shot_id,
  location_id: selected.location_id || undefined,
  character_ids: cast,
  character_id: cast[0],
  prompt: draft.visual_prompt || selected.visual_prompt || "",
  use_location_lora: useLocationLora,
});
const file = String(out.file || "");
const outKey = String(out.out_key || cast[0] || selected.location_id || "");
const url = cast[0]
  ? visualFileUrl(projectId, outKey, "generations", file)
  : visualLocationFileUrl(projectId, outKey, "generations", file);
setGenPreviewUrl(url);
```

Use `out_key` from API: if first character was used for output dir, prefer `visualFileUrl`; if only location, `visualLocationFileUrl`. Safer:

```typescript
const charIds = (out.character_ids as string[]) || cast;
const locId = (out.location_id as string) || selected.location_id;
if (charIds[0]) {
  setGenPreviewUrl(visualFileUrl(projectId, charIds[0], "generations", file));
} else if (locId) {
  setGenPreviewUrl(visualLocationFileUrl(projectId, locId, "generations", file));
}
```

5. Reset `useLocationLora` to `false` when `selectedId` changes.

- [ ] **Step 3: Manual / typecheck**

```bash
cd frontend
npx tsc --noEmit
```

Expected: no new errors in touched files.

- [ ] **Step 4: Commit** (only if user asked)

```bash
git add frontend/src/api/client.ts frontend/src/pages/ShotsPage.tsx
git commit -m "feat(shots): generate keyframe with optional location LoRA"
```

---

### Task 4: Spec status + smoke

**Files:**
- Modify: `docs/superpowers/specs/2026-07-19-optional-location-lora-shot-t2i-design.md` (Status → Implemented)

- [x] **Step 1: Mark spec implemented**

Change header `Status:` to `Implemented`.

- [x] **Step 2: Full related pytest**

```bash
cd backend
python -m pytest tests/test_location_t2i_stack.py tests/test_visual_t2i_shot_route.py -v
```

Expected: PASS.

- [x] **Step 3: Commit docs** (only if user asked)

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Default `use_location_lora=false` | 1, 2, 3 |
| Text → no location LoRA, text still in prompt | 1 |
| True → stack location then characters | 1 |
| Extend `T2IBody` / route shot vs probe | 2 |
| ShotsPage button + checkbox default off | 3 |
| No shot-doc persistence | 3 (state only) |
| Probe path unchanged | 2 |
| Tests for on/off/default | 1, 2 |

## Self-review notes

- No TBD/placeholder steps.
- `use_location_lora` naming consistent across t2i / API / UI.
- Existing stack test updated to opt in so it does not contradict the new default.
