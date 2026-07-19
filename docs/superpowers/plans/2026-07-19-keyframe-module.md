# Keyframe Module (Phase 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist shot T2I outputs as shot-centric keyframe candidates with select/reject, and expose the workflow on ShotsPage.

**Architecture:** New `aivp.keyframes` package (paths + store + generate) thinly wraps `generate_shot_with_loras`, copies PNGs into `projects/{id}/keyframes/{shot_id}/candidates/`, and serves CRUD via `routes_keyframes`. ShotsPage replaces the ephemeral preview with a Keyframe panel.

**Tech Stack:** FastAPI, Pydantic, pytest, React + TypeScript, StubImageBackend in tests.

**Spec:** `docs/superpowers/specs/2026-07-19-keyframe-module-design.md`

## Global Constraints

- Location LoRA default **off** (`use_location_lora=false`).
- Missing character LoRA → **warning**, do not hard-fail.
- Max **3** LoRAs stacked (location first if enabled, then characters in order); overflow → `too_many_loras` warning.
- Sync generate only; no new job queue.
- Source of truth for selection: `selected.json`; shot document update is best-effort.
- Validate `shot_id` / filenames (no `..`, no path separators).
- Prefer stub image backend in tests; no Comfy required.

## File map

| File | Role |
|------|------|
| `backend/src/aivp/keyframes/__init__.py` | Package export |
| `backend/src/aivp/keyframes/paths.py` | `KeyframePaths` |
| `backend/src/aivp/keyframes/store.py` | list/select/reject/delete/read generation |
| `backend/src/aivp/keyframes/generate.py` | resolve shot → generate × N → store |
| `backend/src/aivp/api/routes_keyframes.py` | HTTP API + file serve |
| `backend/src/aivp/api/app.py` | Register router |
| `backend/tests/test_keyframes.py` | Unit + API tests |
| `frontend/src/api/client.ts` | Keyframe client helpers |
| `frontend/src/pages/ShotsPage.tsx` | Keyframe panel UI |

---

### Task 1: `KeyframePaths` + store primitives

**Files:**
- Create: `backend/src/aivp/keyframes/__init__.py`
- Create: `backend/src/aivp/keyframes/paths.py`
- Create: `backend/src/aivp/keyframes/store.py`
- Test: `backend/tests/test_keyframes.py`

**Interfaces:**
- Produces:
  - `KeyframePaths(data_root, project_id)` with `ensure()`, `ensure_shot(shot_id)`, `shot_dir`, `candidates_dir`, `generation_json`, `selected_json`, `review_json`
  - `list_candidates(kpaths, shot_id) -> list[dict]`
  - `read_generation(kpaths, shot_id) -> dict | None`
  - `read_selected(kpaths, shot_id) -> dict | None`
  - `select_keyframe(kpaths, shot_id, filename, *, note="") -> dict`
  - `reject_keyframe(kpaths, shot_id, filename, *, reason="") -> dict`
  - `delete_candidate(kpaths, shot_id, filename) -> dict`
  - `derive_status(kpaths, shot_id) -> str`  # empty|candidates|selected|rejected
  - `next_candidate_stem(kpaths, shot_id) -> str`  # kf_0001 …
  - `safe_shot_id(shot_id) -> str` / `safe_filename(name) -> str` raise `ValueError` on bad input

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_keyframes.py`:

```python
from pathlib import Path
import json

from aivp.keyframes.paths import KeyframePaths
from aivp.keyframes.store import (
    delete_candidate,
    derive_status,
    list_candidates,
    next_candidate_stem,
    reject_keyframe,
    select_keyframe,
)


def test_keyframe_paths_ensure(tmp_path: Path):
    k = KeyframePaths(tmp_path, "p1")
    k.ensure()
    k.ensure_shot("shot_000001")
    assert k.candidates_dir("shot_000001").is_dir()
    assert k.generation_json("shot_000001").parent == k.shot_dir("shot_000001")


def test_select_reject_delete_cycle(tmp_path: Path):
    k = KeyframePaths(tmp_path, "p1")
    k.ensure_shot("shot_1")
    cand = k.candidates_dir("shot_1")
    (cand / "kf_0001.png").write_bytes(b"png")
    (cand / "kf_0001.json").write_text(
        json.dumps({"file": "kf_0001.png", "quality": {"status": "unchecked", "warnings": []}}),
        encoding="utf-8",
    )
    (cand / "kf_0002.png").write_bytes(b"png2")
    (cand / "kf_0002.json").write_text(
        json.dumps({"file": "kf_0002.png", "quality": {"status": "unchecked", "warnings": []}}),
        encoding="utf-8",
    )

    assert derive_status(k, "shot_1") == "candidates"
    assert next_candidate_stem(k, "shot_1") == "kf_0003"

    sel = select_keyframe(k, "shot_1", "kf_0002.png", note="best")
    assert sel["selected_file"] == "kf_0002.png"
    assert sel["review_status"] == "approved"
    assert derive_status(k, "shot_1") == "selected"

    rej = reject_keyframe(k, "shot_1", "kf_0002.png", reason="bad face")
    assert rej["cleared_selection"] is True
    assert derive_status(k, "shot_1") in {"rejected", "candidates"}

    delete_candidate(k, "shot_1", "kf_0001.png")
    files = {c["file"] for c in list_candidates(k, "shot_1")}
    assert "kf_0001.png" not in files
    assert "kf_0002.png" in files
```

- [ ] **Step 2: Run tests — expect fail (import error)**

Run: `py -3 -m pytest backend/tests/test_keyframes.py::test_keyframe_paths_ensure -q`  
Expected: FAIL (module not found)

- [ ] **Step 3: Implement paths + store**

`paths.py`:

```python
from __future__ import annotations
from pathlib import Path

class KeyframePaths:
    def __init__(self, data_root: Path, project_id: str):
        self.data_root = Path(data_root)
        self.project_id = project_id
        self.root = self.data_root / "projects" / project_id / "keyframes"

    def ensure(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)

    def shot_dir(self, shot_id: str) -> Path:
        return self.root / safe_shot_id(shot_id)

    def candidates_dir(self, shot_id: str) -> Path:
        return self.shot_dir(shot_id) / "candidates"

    def generation_json(self, shot_id: str) -> Path:
        return self.shot_dir(shot_id) / "generation.json"

    def selected_json(self, shot_id: str) -> Path:
        return self.shot_dir(shot_id) / "selected.json"

    def review_json(self, shot_id: str) -> Path:
        return self.shot_dir(shot_id) / "review.json"

    def ensure_shot(self, shot_id: str) -> None:
        self.ensure()
        self.shot_dir(shot_id).mkdir(parents=True, exist_ok=True)
        self.candidates_dir(shot_id).mkdir(parents=True, exist_ok=True)

def safe_shot_id(shot_id: str) -> str:
    s = (shot_id or "").strip()
    if not s or "/" in s or "\\" in s or ".." in s:
        raise ValueError(f"invalid_shot_id:{shot_id!r}")
    return s

def safe_filename(name: str) -> str:
    n = (name or "").strip()
    if not n or "/" in n or "\\" in n or ".." in n:
        raise ValueError(f"invalid_filename:{name!r}")
    if not n.lower().endswith(".png"):
        raise ValueError(f"invalid_filename:{name!r}")
    return n
```

`store.py`: implement list/select/reject/delete/derive_status/next_candidate_stem using atomic JSON writes (`path.write_text`). On reject of selected file, clear `selected.json` and append review event. On reject, set sidecar `quality.status=rejected` when json exists.

- [ ] **Step 4: Run tests — expect pass**

Run: `py -3 -m pytest backend/tests/test_keyframes.py::test_keyframe_paths_ensure backend/tests/test_keyframes.py::test_select_reject_delete_cycle -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/keyframes backend/tests/test_keyframes.py
git commit -m "feat(keyframes): add paths and store for shot candidates"
```

---

### Task 2: Generate keyframes via `generate_shot_with_loras`

**Files:**
- Create: `backend/src/aivp/keyframes/generate.py`
- Modify: `backend/tests/test_keyframes.py`

**Interfaces:**
- Consumes: `KeyframePaths`, store helpers, `VisualPaths`, `generate_shot_with_loras`, `get_image_backend` / `ImageBackend`, `ProjectPaths` + shot load
- Produces: `generate_keyframes(project_paths, vpaths, kpaths, backend, shot_id, *, count=4, use_location_lora=False, force=False, prompt_override="", negative_override="", settings=None) -> dict`

Return shape:

```python
{
  "shot_id": str,
  "status": "succeeded",
  "candidates": [{"file": str, "url": str}],  # url filled by route layer optional
  "warnings": list[str],
  "generation": dict,
}
```

- [ ] **Step 1: Write failing tests**

```python
from aivp.keyframes.generate import generate_keyframes
from aivp.keyframes.paths import KeyframePaths
from aivp.keyframes.store import list_candidates, read_generation
from aivp.paths import ProjectPaths
from aivp.visual.image_backend import StubImageBackend
from aivp.visual.paths import VisualPaths
from aivp.visual.profiles import ensure_profile, save_profile


def _seed_shot_project(tmp_path: Path) -> tuple[ProjectPaths, VisualPaths, KeyframePaths]:
    paths = ProjectPaths(tmp_path, "p1")
    paths.ensure()
    v = VisualPaths(tmp_path, "p1")
    v.ensure()
    k = KeyframePaths(tmp_path, "p1")
    k.ensure()
    ch = {"id": "ent_1", "name": "林", "tier": "major", "prompt_zh": "青衣少年"}
    ensure_profile(v, ch)
    doc = {
        "schema_version": 2,
        "shots": [
            {
                "shot_id": "shot_000001",
                "visual_prompt": "立于渡口远眺",
                "negative_prompt": "lowres",
                "cast": ["林"],
                "asset_refs": {"characters": ["ent_1"], "locations": [], "props": []},
                "generation": {},
            }
        ],
    }
    paths.shot_script_json.write_text(
        __import__("json").dumps(doc, ensure_ascii=False), encoding="utf-8"
    )
    return paths, v, k


def test_generate_keyframes_writes_candidates(tmp_path: Path):
    paths, v, k = _seed_shot_project(tmp_path)
    out = generate_keyframes(
        paths, v, k, StubImageBackend(), "shot_000001", count=2
    )
    assert out["status"] == "succeeded"
    assert len(out["candidates"]) == 2
    assert len(list_candidates(k, "shot_000001")) == 2
    gen = read_generation(k, "shot_000001")
    assert gen and gen["candidate_count"] == 2
    assert gen["use_location_lora"] is False


def test_generate_keyframes_warns_when_lora_missing(tmp_path: Path):
    paths, v, k = _seed_shot_project(tmp_path)
    # profile exists but lora_ready false / no file
    out = generate_keyframes(
        paths, v, k, StubImageBackend(), "shot_000001", count=1
    )
    assert any("lora" in w.lower() or "not_ready" in w for w in out["warnings"])
```

- [ ] **Step 2: Run — expect fail**

Run: `py -3 -m pytest backend/tests/test_keyframes.py::test_generate_keyframes_writes_candidates -q`  
Expected: FAIL

- [ ] **Step 3: Implement `generate.py`**

Logic:
1. Load shot script JSON from `paths.shot_script_json` (raise `FileNotFoundError` / `KeyError` if missing shot).
2. Resolve `character_ids` from `asset_refs.characters`; `location_id` from first of `asset_refs.locations` if any.
3. Prompt = override or `visual_prompt` (raise `ValueError` if empty).
4. If `force`: delete all candidates png/json, remove selected.json.
5. Build warnings: for each character id without `lora_ready`/file → `character_lora_not_ready:{id}`; if not use_location_lora and location_id → `location_lora_disabled_by_default`; if use_location_lora and location not ready → `location_lora_not_ready`.
6. Cap character ids for LoRA stacking so total LoRAs ≤ 3 (count location slot if enabled+ready). Truncate excess character ids for LoRA but keep all triggers in prompt if possible — simplest: pass at most (3 - loc_slot) character ids to `generate_shot_with_loras` and warn `too_many_loras`.
7. Loop `count` times: call `generate_shot_with_loras(..., shot_id=shot_id, use_location_lora=..., settings=settings)`; copy `Path(out["path"])` to `candidates/{stem}.png`; write sidecar json; collect candidate entries.
8. Write `generation.json` with prompt, loras from last out, warnings, timestamps.

Use `shutil.copy2` for the PNG.

- [ ] **Step 4: Run — expect pass**

Run: `py -3 -m pytest backend/tests/test_keyframes.py -q`  
Expected: PASS (all current tests)

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/keyframes/generate.py backend/tests/test_keyframes.py
git commit -m "feat(keyframes): generate candidates via shot LoRA stack"
```

---

### Task 3: HTTP routes + app registration

**Files:**
- Create: `backend/src/aivp/api/routes_keyframes.py`
- Modify: `backend/src/aivp/api/app.py`
- Modify: `backend/tests/test_keyframes.py`

**Interfaces:**
- Routes under `/api/projects/{project_id}/keyframes/{shot_id}/...`
- Best-effort shot document patch on select: update shot `generation.keyframe_status` / `keyframe_file` in `shot_script.json` if present

- [ ] **Step 1: Write API test**

```python
from fastapi.testclient import TestClient
from aivp.api.app import create_app
from aivp.config import Settings
from aivp.llm.fake import FakeLlm
from aivp.paths import ProjectPaths


def test_keyframes_api_generate_get_select(tmp_path: Path):
    app = create_app(
        Settings(
            data_root=tmp_path,
            db_url=f"sqlite:///{tmp_path / 'kf.db'}",
            image_backend="stub",
        )
    )
    app.state.llm = FakeLlm(default={})
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "kf"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    # seed visual profile + shot script (same as unit helper but using pid)
    ...
    r = client.post(
        f"/api/projects/{pid}/keyframes/shot_000001/generate",
        json={"count": 2, "use_location_lora": False},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["candidates"]) == 2
    g = client.get(f"/api/projects/{pid}/keyframes/shot_000001")
    assert g.status_code == 200
    assert g.json()["status"] in {"candidates", "empty"}
    fname = body["candidates"][0]["file"]
    s = client.post(
        f"/api/projects/{pid}/keyframes/shot_000001/select",
        json={"filename": fname, "note": "ok"},
    )
    assert s.status_code == 200
    assert s.json()["selected_file"] == fname
    file_r = client.get(
        f"/api/projects/{pid}/keyframes/shot_000001/files/{fname}"
    )
    assert file_r.status_code == 200
```

Fill seed using VisualPaths + shot_script write like Task 2 helper (adapt project id).

- [ ] **Step 2: Run — expect fail (404 routes)**

- [ ] **Step 3: Implement `routes_keyframes.py`**

```python
router = APIRouter(tags=["keyframes"])

class GenerateBody(BaseModel):
    count: int = 4
    use_location_lora: bool = False
    force: bool = False
    prompt_override: str = ""
    negative_override: str = ""

class SelectBody(BaseModel):
    filename: str
    note: str = ""

class RejectBody(BaseModel):
    filename: str
    reason: str = ""
```

Wire endpoints per spec. On generate, attach `url` like `/api/projects/{pid}/keyframes/{shot_id}/files/{file}`. Map exceptions to HTTP 400/404.

Register in `app.py`:

```python
from aivp.api.routes_keyframes import router as keyframes_router
...
app.include_router(keyframes_router, prefix="/api")
```

- [ ] **Step 4: Run full keyframe tests**

Run: `py -3 -m pytest backend/tests/test_keyframes.py -q`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/api/routes_keyframes.py backend/src/aivp/api/app.py backend/tests/test_keyframes.py
git commit -m "feat(api): add keyframe generate/list/select routes"
```

---

### Task 4: Frontend client + ShotsPage Keyframe panel

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/ShotsPage.tsx`

**Interfaces:**
- Produces client helpers listed in spec
- UI replaces ephemeral `onGenerateShot` / `genPreviewUrl` with keyframe state loaded on shot change

- [ ] **Step 1: Add client helpers**

```typescript
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

export const keyframeFileUrl = (
  projectId: string,
  shotId: string,
  filename: string,
) =>
  `/api/projects/${projectId}/keyframes/${encodeURIComponent(shotId)}/files/${encodeURIComponent(filename)}`;
```

- [ ] **Step 2: Wire ShotsPage panel**

On `selectedId` change: `getKeyframes` → set local `kfStatus`, `kfCandidates`, `kfSelected`.

UI block (Chinese labels per spec):
- Status chip
- Checkbox 使用地点 LoRA (reuse existing `useLocationLora` / location ready logic)
- Button 生成关键帧候选 → `generateKeyframes` with `count: 4`, race token
- Grid of candidates with img `keyframeFileUrl`
- Buttons 设为选中 / 退回
- Simple lightbox via existing pattern or `window.open` / inline overlay

Remove or repurpose old `onGenerateShot` ephemeral preview so there is a single path.

- [ ] **Step 3: Manual sanity**

Run backend + frontend; open a project with shots; generate 2 candidates with stub; select one; refresh page and confirm selection persists via GET.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/ShotsPage.tsx
git commit -m "feat(shots): keyframe panel generate/select on ShotsPage"
```

---

### Task 5: Verification + docs touch

**Files:**
- Modify: `docs/superpowers/specs/2026-07-19-keyframe-module-design.md` status → Implemented (after green)
- Optional: short note in `docs/superpowers/plans/` checklist complete

- [ ] **Step 1: Run backend tests**

Run: `py -3 -m pytest backend/tests/test_keyframes.py backend/tests/test_location_t2i_stack.py -q`  
Expected: PASS

- [ ] **Step 2: Mark spec Implemented**

Set **Status:** Implemented in the design spec.

- [ ] **Step 3: Commit + push if requested**

```bash
git add docs/superpowers/specs/2026-07-19-keyframe-module-design.md
git commit -m "docs: mark keyframe module Phase 1 implemented"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| Directory layout + selected/generation/review | 1 |
| Thin wrap `generate_shot_with_loras` | 2 |
| Warnings + LoRA cap 3 | 2 |
| APIs generate/get/select/reject/delete/files | 3 |
| ShotsPage panel | 4 |
| Tests stub | 1–3 |
| Non-goals (I2V, VisualPage split, etc.) | deferred |

## Plan self-review

- No TBD steps; concrete code and commands.
- Interfaces match across tasks (`KeyframePaths`, `generate_keyframes` return).
- Sync-only; force clears candidates; location LoRA default false.
