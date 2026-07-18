# Story-Driven Expression Dimensions Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Derive per-character `expression_dims` from story emotions into the Story Bible, and have the visual layer generate expression sheets from those dims instead of a fixed 8-slot catalog.

**Architecture:** Clustering lives in `aivp.bible.expression_dims` (pure functions). Bible character cards own `expression_dims[]` + `default_expression`. Visual `resolve_sheet_slots` reads merged bible; legacy `EXPRESSION_SLOTS` remain as framing fallback. Visual profile only stores generation state per dim id.

**Tech Stack:** Python 3.12, FastAPI, existing bible merge (`persist_merged_bible`), visual sheets pipeline, pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-story-driven-expression-dims-design.md`

## Global Constraints

- Do not wipe approved dims on rebuild (merge mode).
- Always ensure `expr_calm` unless explicitly rejected.
- Identity look fields must not bake resting smile (use `default_expression`).
- Prefer TDD: failing test → implement → green.
- Do not commit unless the user explicitly asks.

## File Map

| File | Responsibility |
|---|---|
| `backend/src/aivp/bible/expression_dims.py` | Synonym map, cluster emotions → dims, framing templates |
| `backend/src/aivp/bible/meta.py` or new hook | Optional: attach dims during persist (or leave to explicit API) |
| `backend/src/aivp/api/routes_bible.py` | rebuild / patch expression-dims endpoints |
| `backend/src/aivp/visual/sheets.py` | `resolve_sheet_slots` from bible dims |
| `backend/src/aivp/visual/trainset_check.py` | Score against story dims |
| `backend/src/aivp/api/routes_visual.py` | Pass character dims into sheet job |
| `frontend/src/pages/VisualPage.tsx` | List dims + generate selected |
| `backend/tests/test_expression_dims.py` | Clustering + merge tests |
| `backend/tests/test_character_sheets.py` | Bible-driven slot resolution |

---

### Task 1: Clustering module (core)

**Files:**
- Create: `backend/src/aivp/bible/expression_dims.py`
- Create: `backend/tests/test_expression_dims.py`

- [x] **Step 1:** Write failing tests
- [x] **Step 2:** Run pytest — expect fail
- [x] **Step 3:** Implement clustering module
- [x] **Step 4:** Re-run tests — pass

---

### Task 2: Bible API — rebuild dims

- [x] **Step 1–4:** Endpoints + API test green

---

### Task 3: Backfill 青渡川V5 majors

- [x] **Step 1–2:** Majors have expression_dims (苏婆婆 4 dims, 林砚之 8, …)

---

### Task 4: Visual sheets consume bible dims

- [x] **Step 1–5:** resolve_sheet_slots + list payload + tests

---

### Task 5: Trainset check + UI (MVP)

- [x] **Step 1–4:** trainset dim-aware warnings; VisualPage dim buttons + rebuild

---

### Task 6: Verification

- [x] **Step 1:** Related pytest green (24 passed)
- [ ] **Step 2:** Manual UI smoke (user)

---

## Done when

- Majors in 青渡川V5 have story-derived `expression_dims` on bible cards.
- Expression sheet generation uses those dims (+ calm), not the fixed 8 by default.
- Tests cover clustering merge + slot resolution.
