# Location LoRA Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap per-project major-location establishing look-lock + empty-scene curated trainset, with description QA, vision judge gates, location-local retunes, progress API, human confirm UI, and shot t2i stacking with character LoRAs.

**Architecture:** Parallel tree under `visual/locations/{id}/` mirroring character bootstrap. New modules `location_*` / `location_bootstrap` reuse patterns from `bootstrap.py`, `judge.py`, `look_lock.py` without mixing character dirs. Job kind `visual_location_bootstrap`. Frontend VisualPage gains a 地点 tab.

**Tech Stack:** FastAPI, Comfy/stub image backend, Ollama vision judge, React VisualPage, existing kohya train cmd pattern.

**Spec:** `docs/superpowers/specs/2026-07-19-location-lora-bootstrap-design.md`

## Global Constraints

- Majors only; training images must be empty scenes (no readable people).
- Hard retry caps from spec; no infinite loops.
- Do not auto-run LoRA train; stop at `awaiting_confirm`.
- Never use character look-lock as location img2img base.
- Trigger format: `slug(name)_loc_aivp`.
- Work on `master` unless user says otherwise.

## File map

| File | Role |
|------|------|
| `backend/src/aivp/visual/paths.py` | `locations_dir`, `location_dir`, candidates/sheets/curated/lora helpers |
| `backend/src/aivp/config.py` | `location_bootstrap_*`, `location_lora_strength` |
| `backend/src/aivp/visual/location_profiles.py` | load majors, ensure/save profile, status, trigger |
| `backend/src/aivp/visual/location_description_qa.py` | evidence QA for location prompt_zh / palette / materials |
| `backend/src/aivp/visual/location_judge.py` | empty-scene checks + `is_location_look_lock_eligible` |
| `backend/src/aivp/visual/location_bootstrap_tuning.py` | location-local patches |
| `backend/src/aivp/visual/location_prompts.py` | empty establishing / expand prompts + negatives |
| `backend/src/aivp/visual/location_candidates.py` | generate empty plates |
| `backend/src/aivp/visual/location_look_lock.py` | set/clear establishing lock |
| `backend/src/aivp/visual/location_sheets.py` | angle / TOD / weather / material slots |
| `backend/src/aivp/visual/location_bootstrap.py` | orchestrator A–G |
| `backend/src/aivp/visual/location_curate.py` | copy keepers → curated + captions |
| `backend/src/aivp/api/routes_visual.py` | location list/bootstrap/confirm/swap/train hooks |
| `backend/src/aivp/visual/t2i.py` (+ shot caller if any) | stack location + character LoRAs |
| `frontend/src/api/client.ts`, `VisualPage.tsx` | 地点 tab + bootstrap UI |
| `backend/tests/test_location_*.py` | unit + API tests |

---

### Task 1: Paths + config knobs

**Files:**
- Modify: `backend/src/aivp/visual/paths.py`
- Modify: `backend/src/aivp/config.py`
- Test: `backend/tests/test_location_paths.py`

**Interfaces:**
- Produces: `VisualPaths.locations_dir`, `location_dir(id)`, `ensure_location(id)`, `location_profile_json(id)`, `location_candidates_dir`, `location_sheets_dir`, `location_curated_dir`, `location_lora_dir`
- Produces settings: `location_bootstrap_lock_count=14`, `location_bootstrap_lock_batch_retries=3`, `location_bootstrap_slot_retries=3`, `location_bootstrap_desc_rewrite_retries=3`, `location_bootstrap_archive_top_k=3`, `location_lora_strength=0.7`

- [ ] **Step 1: Write failing test**

```python
from pathlib import Path
from aivp.visual.paths import VisualPaths

def test_location_dirs(tmp_path: Path):
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    v.ensure_location("loc_0001")
    assert v.location_dir("loc_0001").exists()
    assert v.location_candidates_dir("loc_0001").exists()
    assert (v.root / "locations" / "loc_0001").exists()
```

- [ ] **Step 2: Run test — expect FAIL** (`ensure_location` missing)

Run: `pytest backend/tests/test_location_paths.py -v`

- [ ] **Step 3: Implement paths + Settings fields**

Add to `VisualPaths.ensure`: create `self.locations_dir = self.root / "locations"`.  
Mirror `ensure_character` as `ensure_location` with candidates/curated/lora/generations/sheets/look_lock.

- [ ] **Step 4: Run test — expect PASS**

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/visual/paths.py backend/src/aivp/config.py backend/tests/test_location_paths.py
git commit -m "Add visual location path helpers and bootstrap config knobs."
```

---

### Task 2: Location profiles

**Files:**
- Create: `backend/src/aivp/visual/location_profiles.py`
- Test: `backend/tests/test_location_profiles.py`

**Interfaces:**
- Consumes: `VisualPaths.ensure_location`, bible location cards
- Produces:
  - `load_major_locations(bible: dict) -> list[dict]`
  - `location_trigger(name: str) -> str`  # ends with `_loc_aivp`
  - `ensure_location_profile(vpaths, location: dict) -> dict`
  - `save_location_profile(vpaths, profile: dict) -> dict`
  - `location_status(vpaths, location_id, profile) -> dict`  # includes look_lock_archive, bootstrap_status

- [ ] **Step 1: Failing tests**

```python
def test_location_trigger_suffix():
    from aivp.visual.location_profiles import location_trigger
    assert location_trigger("青渡川").endswith("_loc_aivp")

def test_ensure_profile_from_bible_card(tmp_path):
    from aivp.config import Settings
    from aivp.visual.paths import VisualPaths
    from aivp.visual.location_profiles import ensure_location_profile, read_location_profile
    v = VisualPaths(tmp_path, "p1"); v.ensure()
    loc = {"id": "loc_1", "name": "渡口", "tier": "major", "prompt_zh": "晨雾渡口，青石埠头"}
    p = ensure_location_profile(v, loc)
    assert p["trigger"].endswith("_loc_aivp")
    assert p["prompt_zh"]
    assert read_location_profile(v.location_profile_json("loc_1"))["character_id"] is None  # no char field
    assert p.get("location_id") == "loc_1"
```

Use `location_id` key (not `character_id`). Reuse slug helper from character profiles if exported; otherwise copy small slug.

- [ ] **Step 2: Implement module**

Seed profile from bible: `prompt_zh`, `palette`, `materials`, `era_mood`, `time_of_day_default`, `weather_default`, `establishing_shot`. Defaults: `train_status=not_started`, `bootstrap_status=not_started`.

- [ ] **Step 3: pytest PASS + commit**

```bash
git commit -m "Add location visual profiles and major location loader."
```

---

### Task 3: Location description QA

**Files:**
- Create: `backend/src/aivp/visual/location_description_qa.py`
- Test: `backend/tests/test_location_description_qa.py`

**Interfaces:**
- Produces: `qa_location_description(profile, entity, llm=None, max_rewrites=3) -> {ok, profile, warnings, rewrites}`

- [ ] **Step 1: Failing tests**

```python
def test_qa_pass_when_materials_in_evidence():
    profile = {"prompt_zh": "青石埠头渡口", "palette": ["青灰"], "materials": ["青石"]}
    entity = {"evidence": "青石铺就的埠头，江雾弥漫"}
    from aivp.visual.location_description_qa import qa_location_description
    out = qa_location_description(profile, entity, llm=None)
    assert out["ok"] is True

def test_qa_marks_ungrounded_when_no_evidence():
    profile = {"prompt_zh": "金碧辉煌龙宫", "materials": ["琉璃"]}
    entity = {"evidence": "小河渡口"}
    out = qa_location_description(profile, entity, llm=None)
    # Without LLM: ok False or warnings containing ungrounded; inferred_fields updated
    assert out["ok"] is False or out["warnings"]
```

Heuristic (no LLM): require at least one material/palette token or name overlap with evidence; else fail. With LLM: constrained rewrite like character QA.

- [ ] **Step 2: Implement + pytest PASS + commit**

```bash
git commit -m "Add location description QA against novel evidence."
```

---

### Task 4: Location judge (empty-scene lock eligibility)

**Files:**
- Create: `backend/src/aivp/visual/location_judge.py` (or extend `judge.py` with `mode="location"` — prefer **separate module** calling shared vision client to avoid breaking character prompts)
- Test: `backend/tests/test_location_judge.py`

**Interfaces:**
- Produces: `judge_location_image(vision, profile, image_path, *, slot_key=None) -> dict`
- Produces: `is_location_look_lock_eligible(judged: dict) -> bool`

Eligible requires checks pass: `no_people`, `place_readable`, `establishing_or_env` (for lock/candidate slots), `style_match` soft-ok if score high.

- [ ] **Step 1: Failing tests on normalize / eligibility**

```python
def test_eligible_requires_no_people():
    from aivp.visual.location_judge import is_location_look_lock_eligible
    judged = {
        "pass": True,
        "score": 0.8,
        "checks": {
            "no_people": {"pass": False, "note": "face"},
            "place_readable": {"pass": True},
            "establishing_or_env": {"pass": True},
            "style_match": {"pass": True},
            "not_character_sheet": {"pass": True},
        },
        "failure_tags": ["has_people"],
    }
    assert is_location_look_lock_eligible(judged) is False

def test_eligible_ok():
    judged = {
        "pass": True,
        "score": 0.8,
        "checks": {
            "no_people": {"pass": True},
            "place_readable": {"pass": True},
            "establishing_or_env": {"pass": True},
            "style_match": {"pass": True},
            "not_character_sheet": {"pass": True},
        },
        "failure_tags": [],
    }
    assert is_location_look_lock_eligible(judged) is True
```

- [ ] **Step 2: Implement judge prompt JSON schema for location + normalize failure tags (`has_people`, `place_unreadable`, `too_tight_crop`, `busy_wrong_place`)**

- [ ] **Step 3: pytest PASS + commit**

```bash
git commit -m "Add empty-scene location look-lock judge."
```

---

### Task 5: Location bootstrap tuning

**Files:**
- Create: `backend/src/aivp/visual/location_bootstrap_tuning.py`
- Test: `backend/tests/test_location_bootstrap_tuning.py`

**Interfaces:** Mirror `bootstrap_tuning.py` but path = `location_dir / bootstrap_tuning.json`.

```python
def patches_from_failure_tags(tags) -> dict:
    # has_people -> extra_negative people/face; full_empty_boost
    # place_unreadable -> place_token_boost; candidate_cfg
    # too_tight_crop -> wide_establishing_boost
    ...
```

- [ ] Tests for merge + has_people patch
- [ ] Implement + commit

```bash
git commit -m "Add location-local bootstrap tuning from judge tags."
```

---

### Task 6: Location prompts + candidates + look_lock + sheets

**Files:**
- Create: `location_prompts.py`, `location_candidates.py`, `location_look_lock.py`, `location_sheets.py`, `location_curate.py`
- Test: `backend/tests/test_location_candidates.py` (stub backend)

**Interfaces:**
- `build_location_candidate_prompt(profile, view: str) -> str` — empty scene, no people
- `location_negative_for(profile) -> str` — person, face, portrait, character sheet, crowd
- `generate_location_candidates_for(vpaths, location, backend, *, count, should_cancel=None) -> {files}`
- `set_location_look_lock(vpaths, location_id, *, folder, filename, denoise=0.55)`
- `LOCATION_SHEET_SLOTS`: e.g. `establishing_wide`, `angle_three_quarter`, `tod_dawn`, `tod_dusk`, `weather_fog`, `material_stone`, `material_wood`
- `generate_location_sheets(...)`
- `curate_location_images(vpaths, location_id, keep, keep_sheets=None)`

- [ ] **Step 1: Stub generate test**

```python
def test_generate_location_candidates_writes_pngs(tmp_path):
    from aivp.visual.image_backend import StubImageBackend
    from aivp.visual.location_candidates import generate_location_candidates_for
    from aivp.visual.location_profiles import ensure_location_profile
    from aivp.visual.paths import VisualPaths
    v = VisualPaths(tmp_path, "p1"); v.ensure()
    loc = {"id": "loc_1", "name": "渡口", "tier": "major", "prompt_zh": "晨雾青石渡口"}
    ensure_location_profile(v, loc)
    out = generate_location_candidates_for(v, loc, StubImageBackend(), count=2)
    assert len(out["files"]) == 2
    # caption/prompt txt should mention empty / no people
    txt = (v.location_candidates_dir("loc_1") / out["files"][0]).with_suffix(".txt").read_text(encoding="utf-8")
    assert "people" in txt.lower() or "empty" in txt.lower() or "无人" in txt or "no people" in txt.lower()
```

When look_lock present, img2img from **location** ref only; apply location bootstrap_tuning extras.

- [ ] **Step 2: Implement modules + pytest PASS**

- [ ] **Step 3: Commit**

```bash
git commit -m "Add location empty-scene generation, look-lock, sheets, and curate."
```

---

### Task 7: Location bootstrap orchestrator

**Files:**
- Create: `backend/src/aivp/visual/location_bootstrap.py`
- Test: `backend/tests/test_location_bootstrap.py`

**Interfaces:**
- `bootstrap_location(vpaths, location, backend, *, settings, vision=None, llm=None, entity=None, should_cancel=None, on_progress=None) -> dict`
- `bootstrap_locations_project(vpaths, bible, backend, *, settings, ...) -> dict`
- `confirm_location_bootstrap`, `skip_location_bootstrap`, `swap_location_look_lock`

Steps A–F as in character `bootstrap.py`, but call location_* modules and `is_location_look_lock_eligible`. Heuristic judge when `vision is None` (all empty-scene checks pass).

- [ ] **Step 1: Failing integration test**

```python
def test_bootstrap_location_awaiting_confirm(tmp_path):
    from aivp.config import Settings
    from aivp.visual.image_backend import StubImageBackend
    from aivp.visual.location_bootstrap import bootstrap_location
    from aivp.visual.location_look_lock import location_look_lock_ref_path
    from aivp.visual.location_profiles import read_location_profile
    from aivp.visual.paths import VisualPaths
    settings = Settings(data_root=tmp_path, image_backend="stub")
    settings.location_bootstrap_lock_count = 10
    settings.location_bootstrap_lock_batch_retries = 1
    settings.location_bootstrap_slot_retries = 1
    v = VisualPaths(tmp_path, "p1"); v.ensure()
    loc = {"id": "loc_1", "name": "渡口", "tier": "major", "prompt_zh": "青石渡口晨雾", "materials": ["青石"]}
    entity = {"id": "loc_1", "evidence": "青石埠头，江雾"}
    out = bootstrap_location(v, loc, StubImageBackend(), settings=settings, vision=None, entity=entity)
    assert out["status"] == "awaiting_confirm"
    assert location_look_lock_ref_path(v, "loc_1")
    assert read_location_profile(v.location_profile_json("loc_1"))["bootstrap_status"] == "awaiting_confirm"
    assert list(v.location_curated_dir("loc_1").glob("*.png"))
```

- [ ] **Step 2: Implement orchestrator + confirm/swap/skip**

- [ ] **Step 3: pytest PASS + commit**

```bash
git commit -m "Add location bootstrap orchestrator with human confirm gate."
```

---

### Task 8: API routes + API test

**Files:**
- Modify: `backend/src/aivp/api/routes_visual.py`
- Test: `backend/tests/test_api_visual_location_bootstrap.py`

**Endpoints:**
- `GET /projects/{id}/visual/locations`
- `POST /projects/{id}/visual/locations/bootstrap` → kind `visual_location_bootstrap`
- `POST .../visual/locations/{lid}/bootstrap/confirm|skip`
- `POST .../visual/locations/{lid}/bootstrap/swap-look-lock`
- Serve files under folder `locations` path: prefer  
  `GET .../visual/locations/{lid}/files/{folder}/{filename}`  
  (keep character file route unchanged)

Progress job fields: `current_location_id`, `bootstrap_step`, `progress_note`, `progress_done/total`.

When `image_backend=="stub"`, force `vision=None` (same as character bootstrap).

- [ ] **Step 1: API test with TestClient + stub + entities/bible locations**

```python
def test_location_bootstrap_job_confirm(tmp_path):
    # seed bible.locations major; POST bootstrap; GET job succeeded;
    # list locations bootstrap_status awaiting_confirm; confirm -> curated_ready
```

- [ ] **Step 2: Implement routes + pytest PASS + commit**

```bash
git commit -m "Expose location bootstrap API job, confirm, and swap-look-lock."
```

---

### Task 9: Frontend 地点 tab

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/VisualPage.tsx`
- Optional: `frontend/src/styles.css` for tab

**Client:**
- `listVisualLocations`, `startVisualLocationBootstrap`, `confirmVisualLocationBootstrap`, `skipVisualLocationBootstrap`, `swapVisualLocationBootstrapLookLock`, `visualLocationFileUrl`

**UI:**
- Tab switch 角色 | 地点
- 「初始化地点训练集」 / 「全部 major 地点」
- Progress notes for `visual_location_bootstrap`
- Review card: archive thumbs, confirm, skip
- Show `bootstrap_status` flag in nav

- [ ] Manual smoke: open Visual page, tab switches, button disabled when busy
- [ ] Commit

```bash
git commit -m "Add VisualPage locations tab for bootstrap review and confirm."
```

---

### Task 10: Shot t2i stack location + character LoRAs

**Files:**
- Modify: `backend/src/aivp/visual/t2i.py` (or new `shot_t2i.py` if cleaner)
- Modify: caller in `routes_visual.py` / shot generate route if exists
- Test: `backend/tests/test_location_t2i_stack.py`

**Interfaces:**
- `generate_shot_with_loras(vpaths, backend, *, location_id=None, character_ids=None, prompt, ...) -> dict`
- Load location LoRA strength from settings `location_lora_strength` when profile `lora_ready`
- Prompt prefix: location trigger + env summary, then character triggers

Inspect `ImageBackend.generate` / Comfy workflow first. Required outcome of this task: support `loras: list[dict]` with `{name, strength}` (location first, then characters). If Comfy workflow currently accepts only one LoRA node, extend the workflow JSON to chain multiple LoRA loaders; stub backend must record the full `loras` list for assertions.

- [ ] Read current `ImageBackend.generate` signature; extend to `loras: list[dict[str, Any]] | None = None` (keep single `lora_name` as backward-compat wrapper)
- [ ] Unit test with stub recording `loras` kwargs (location + one character)
- [ ] Commit

```bash
git commit -m "Stack location and character LoRAs in shot t2i generation."
```

---

## Verification

```bash
cd backend
pytest tests/test_location_paths.py tests/test_location_profiles.py tests/test_location_description_qa.py tests/test_location_judge.py tests/test_location_bootstrap_tuning.py tests/test_location_candidates.py tests/test_location_bootstrap.py tests/test_api_visual_location_bootstrap.py tests/test_location_t2i_stack.py -q
```

Optional: one Comfy smoke on a single major location with vision model available.

## Spec coverage checklist

| Spec item | Task |
|-----------|------|
| Parallel `visual/locations/` | 1–2 |
| Description QA | 3 |
| Empty-scene judge / lock eligibility | 4 |
| Location-local tuning | 5 |
| Candidates / lock / sheets / curate | 6 |
| Bootstrap A–G + confirm/swap | 7–8 |
| Frontend tab | 9 |
| t2i stacking | 10 |
| No auto train | 7–8 (confirm gate only) |
| Stub skips vision | 8 |

---

## Self-review notes

- No genre pack / unified assets refactor in this plan (spec follow-ups).
- Character routes and `visual/characters/` untouched except shared jobs list and optional t2i stacking.
- Multi-LoRA Comfy support may require workflow JSON update inside Task 10 — inspect `comfy_backend.py` before coding.
