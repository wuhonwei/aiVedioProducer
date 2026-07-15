# Distinct Character Looks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Major character looks are evidence-seeded and mutually distinct; collisions fail `06_enrich_assets` hard.

**Architecture:** Add `character_looks.py` for seed + signature + validation; wire into `ensure_character_card` / `build_assets`; ban shared major template defaults.

**Tech Stack:** Existing FastAPI backend, pytest, FakeLlm.

## Global Constraints

- Hard fail on major look collisions (spec B); default `enrich_require_distinct_characters=True`
- No shared major face/wardrobe defaults across cards
- Minor characters unchecked
- Commit + push when done (user preference)

---

### Task 1: Heuristic seed + signature + validator

**Files:**
- Create: `backend/src/aivp/pipeline/character_looks.py`
- Test: `backend/tests/test_character_looks.py`

**Interfaces:**
- Produces: `seed_character_look(entity: dict) -> dict`, `look_signature(card: dict) -> str`, `assert_major_characters_distinct(characters: list[dict]) -> None` (raises `ValueError`)

- [ ] **Step 1: Write failing tests** in `test_character_looks.py` for: (a) 林砚之/苏婆婆/周大人 seeds differ; (b) identical signatures raise; (c) empty prompt_zh raises among majors.

- [ ] **Step 2: Implement `character_looks.py`** with evidence/alias rules + stable name-hash palette fallback + `look_signature` + `assert_major_characters_distinct`.

- [ ] **Step 3: pytest passes**

---

### Task 2: Wire coerce + enrich hard fail

**Files:**
- Modify: `backend/src/aivp/pipeline/coerce_assets.py` (`ensure_character_card`)
- Modify: `backend/src/aivp/pipeline/enrich.py` (`_llm_batch` context, `build_assets` validate before return)
- Modify: `backend/src/aivp/config.py` (`enrich_require_distinct_characters: bool = True`)
- Modify: `backend/tests/test_enrich.py`

**Interfaces:**
- Consumes: Task 1 functions
- `ensure_character_card` uses per-entity seed instead of shared major defaults
- `build_assets` calls assert when setting enabled (pass settings or flag)

- [ ] **Step 1: Failing test** — FakeLlm returns empty items; three entities with distinct evidence still get distinct prompts; colliding cards fail.

- [ ] **Step 2: Implement wiring** — remove shared defaults; enrich prompt includes evidence; validate before write in `run_enrich`.

- [ ] **Step 3: pytest** `test_character_looks.py` `test_enrich.py` green

- [ ] **Step 4: Commit + push**

---

## Spec coverage

| Spec item | Task |
|-----------|------|
| Evidence heuristic seeds | 1 |
| Ban shared major template | 2 |
| LLM batch gets evidence + anti-clone instruction | 2 |
| Hard validation / fail enrich | 1+2 |
| Config flag default true | 2 |
| Fixture tests 林/苏/周 + collision | 1+2 |
