# Task 5 Report: Verification + docs touch

**Date:** 2026-07-19  
**Branch:** master  
**Status:** Complete

## Pytest summary

**Command:**
```bash
py -3 -m pytest backend/tests/test_keyframes.py backend/tests/test_location_t2i_stack.py -q
```

**Working directory:** `D:\Develop\aiVedioProducer`

**Result:** PASS

```
............                                                             [100%]
============================== warnings summary ===============================
C:\Users\admin\AppData\Local\Programs\Python\Python312\Lib\site-packages\fastapi\testclient.py:1
  C:\Users\admin\AppData\Local\Programs\Python\Python312\Lib\site-packages\fastapi\testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
    from starlette.testclient import TestClient as TestClient  # noqa

-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html
12 passed, 1 warning in 0.56s
```

| Metric | Value |
|--------|-------|
| Tests run | 12 |
| Passed | 12 |
| Failed | 0 |
| Warnings | 1 (StarletteDeprecationWarning: httpx vs httpx2) |
| Duration | 0.56s |

**Test files:**
- `backend/tests/test_keyframes.py`
- `backend/tests/test_location_t2i_stack.py`

## Docs update

**File:** `docs/superpowers/specs/2026-07-19-keyframe-module-design.md`

**Change:** `**Status:** Approved for implementation` → `**Status:** Implemented`

## Commit

```
docs: mark keyframe module Phase 1 implemented
```

## Spec coverage checklist (Phase 1)

| Spec requirement | Status |
|------------------|--------|
| Directory layout + selected/generation/review | Implemented (Tasks 1–3) |
| Thin wrap `generate_shot_with_loras` | Implemented (Task 2) |
| Warnings + LoRA cap 3 | Implemented (Task 2) |
| APIs generate/get/select/reject/delete/files | Implemented (Task 3) |
| ShotsPage panel | Implemented (Task 4) |
| Tests stub | Implemented (Tasks 1–3) |
| Non-goals (I2V, VisualPage split, etc.) | Deferred per spec |

## Acceptance (MVP)

All six MVP acceptance criteria from the design spec are covered by passing tests and prior task implementation.

---

## Final review fixes (2026-07-19)

**Commit:** `fix(keyframes): cast fallback, delete UI, and surface warnings`

### Changes

1. **Cast/name fallback (`generate.py`)** — When `asset_refs.characters` / `asset_refs.locations` are empty, resolve IDs from shot cast / location names using `build_name_to_id_map` (same spirit as ShotsPage / `shot_upgrade`).
2. **Delete client + UI** — Added `deleteKeyframeCandidate` to `frontend/src/api/client.ts`; ShotsPage keyframe panel adds per-candidate **删除** button with race-guarded `reloadKeyframes`.
3. **Surface warnings** — ShotsPage shows up to 5 warnings from generate/get responses (`warnings` + `generation.warnings`) under the keyframe panel.

### Tests

**Command:** `py -3 -m pytest backend/tests/test_keyframes.py -q`

**Result:** PASS — 9 passed, 1 warning (StarletteDeprecationWarning), ~0.57s

**New test:** `test_generate_keyframes_resolves_cast_names_when_asset_refs_empty`

**Frontend:** `npm run build` — PASS (tsc + vite build)
