# Auto Trainset Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bootstrap major-character look-lock + curated trainset with description QA, vision judge gates, character-local retunes, progress API, and human confirm UI.

**Architecture:** New `aivp.visual.bootstrap` package orchestrates per-character steps A–F; reuses `candidates` / `sheets` / `look_lock` / `judge` / `curate`. Job kind `visual_bootstrap` streams progress. Character-local `bootstrap_tuning.json`. Frontend VisualPage panel for progress + confirm/swap.

**Tech Stack:** FastAPI, existing Comfy backend, Ollama vision judge, React VisualPage.

## Global Constraints

- Majors only; plain background for all character gens.
- Hard retry caps from spec; no infinite loops.
- Do not auto-run LoRA train; stop at `awaiting_confirm`.
- Character LoRA: face/wardrobe/pose/expression only (no scene LoRA here).

## File map

| File | Role |
|------|------|
| `backend/src/aivp/visual/description_qa.py` | Evidence-grounded prompt_zh/wardrobe QA + rewrite |
| `backend/src/aivp/visual/bootstrap_tuning.py` | Load/save char-local patches from failure tags |
| `backend/src/aivp/visual/bootstrap.py` | Orchestrator A–F |
| `backend/src/aivp/visual/judge.py` | Extend checks for lock eligibility |
| `backend/src/aivp/config.py` | Bootstrap knobs |
| `backend/src/aivp/api/routes_visual.py` | Job start/status/confirm/swap endpoints |
| `frontend/src/api/client.ts` + `VisualPage.tsx` | Progress + review UI |
| `backend/tests/test_description_qa.py` etc. | Unit tests |

---

## Task 1: Description QA

**Files:** `description_qa.py`, `tests/test_description_qa.py`

- [ ] Test: wardrobe claim with no evidence → fail or rewrite flag
- [ ] Test: evidence contains 粗布 → pass
- [ ] Implement `qa_character_description(profile, entity, llm=None) -> {ok, profile, warnings, rewrites}`
- [ ] Cap rewrites via settings; mark `inferred_fields` when guessing
- [ ] Run pytest

## Task 2: Lock eligibility + judge extensions

**Files:** `judge.py`, `tests/test_judge_lock.py`

- [ ] Extend judge user prompt / normalize for `framing_full_body`, `outfit_complete`, `background_plain`
- [ ] `is_look_lock_eligible(judged) -> bool`
- [ ] Unit tests on normalize hard-fail half_body / busy_bg

## Task 3: Character-local bootstrap tuning

**Files:** `bootstrap_tuning.py`, `tests/test_bootstrap_tuning.py`

- [ ] `load/save_bootstrap_tuning(vpaths, cid)`
- [ ] `patches_from_failure_tags(tags) -> dict`
- [ ] `merge_tuning(existing, patches)`
- [ ] Tests

## Task 4: Bootstrap orchestrator (core)

**Files:** `bootstrap.py`, `tests/test_bootstrap.py` (stub backend + fake vision)

- [ ] `bootstrap_character(...)` steps A–F with caps
- [ ] `bootstrap_project(...)` over majors + progress callback
- [ ] Archive Top-K; set look_lock; expand sheets/candidates with per-slot retry
- [ ] StubImageBackend + FakeVision path in tests (no Comfy)

## Task 5: Config + API

**Files:** `config.py`, `routes_visual.py`, client types

- [ ] Settings defaults from spec
- [ ] `POST .../visual/bootstrap` → job
- [ ] `GET` job progress payload
- [ ] `POST .../bootstrap/confirm`, `POST .../bootstrap/swap-look-lock`
- [ ] API tests with TestClient

## Task 6: Frontend MVP

**Files:** `client.ts`, `VisualPage.tsx`, tests if present

- [ ] Button「初始化视觉训练集」
- [ ] Progress list per character/step
- [ ] Confirm / swap look-lock / show warnings
- [ ] Manual smoke checklist

## Task 7: Wire plain-bg + framing into candidate prompts for bootstrap

- [ ] Bootstrap calls generate with forced plain bg extras (or profile flag)
- [ ] Ensure lock batch uses txt2img full-body framing from prior prompt work

---

## Verification

- `pytest` for new modules + existing look_lock/judge/visual tests
- Optional Comfy smoke one character with vision if available
