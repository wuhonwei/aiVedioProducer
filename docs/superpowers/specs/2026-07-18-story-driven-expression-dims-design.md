# Story-Driven Character Expression Dimensions

**Date:** 2026-07-18  
**Status:** Approved — implemented (MVP)  
**Scope:** Text layer (Story Bible) owns which expressions a character needs; visual layer consumes and generates them as independent dimensions.

---

## 1. Problem

Today the visual layer hard-codes eight expression slots for every major character:

`calm / smile / happy / confused / angry / sad / surprised / shy`

That causes three failures:

1. **Wrong coverage** — characters get expressions they never show in the story, and miss ones they do (e.g. 震惊、关心、咬牙忍痛).
2. **Prompt collision** — resting smile cues baked into identity (`抿唇带笑`) fight strong-emotion sheets.
3. **Waste** — full 8-sheet runs are expensive and hard to QA when most slots are filler.

Story extraction already emits `emotion` on events / character mentions, but nothing aggregates that into a per-character expression plan.

---

## 2. Goals

- Each character has an **expression dimension table** derived from story evidence.
- Each dimension is **independent**: own id, evidence, framing, generate/curate/train status.
- Dimensions can **grow incrementally** as more volumes are processed.
- Visual generation **consumes** the table; it does not invent the catalog.
- Keep one optional **resting / calm** dimension for look-lock and candidate baselines.

### Non-goals (this design)

- Replacing turnaround (front/side/back) sheets.
- Full facial-performance / lip-sync animation.
- Auto-approving LoRA from expressions without human probe.

---

## 3. Ownership Split

| Layer | Owns | Does not own |
|---|---|---|
| **Story Bible character card** | `expression_dims[]` (what emotions are needed + evidence) | Generated PNGs, denoise knobs |
| **Visual profile** | Per-dim generation artifacts & train inclusion | Redefining which dims exist |

```text
正文 / enrich.emotion
        │
        ▼
  Bible: expression_dims[]     ← source of truth (editable)
        │
        ▼
  Visual: generate sheet per dim → curate → LoRA package
```

---

## 4. Data Model

### 4.1 Bible — `characters[].expression_dims[]`

```json
{
  "id": "expr_shocked",
  "label": "震惊",
  "emotion": "震惊、好奇",
  "framing": "surprised shocked expression, wide eyes, raised eyebrows, open mouth...",
  "evidence": [
    {
      "text": "林砚之发现母亲留下的信和玉佩…",
      "source": "events_enriched",
      "ref": "evt_…"
    }
  ],
  "priority": 2,
  "status": "proposed"
}
```

| Field | Meaning |
|---|---|
| `id` | Stable slug `expr_<english_or_hash>`; unique per character |
| `label` | Short Chinese UI label |
| `emotion` | Canonical emotion tag (may be multi-word from enrich) |
| `framing` | English (+ optional ZH) prompt fragment for face sheet |
| `evidence` | Story quotes / event refs that justify this dim |
| `priority` | Lower = generate first (1 = must-have) |
| `status` | `proposed` \| `approved` \| `rejected` \| `stale` |

**Always ensure** (unless explicitly rejected):

```json
{
  "id": "expr_calm",
  "label": "平静",
  "emotion": "平静",
  "framing": "…neutral resting face…",
  "evidence": [],
  "priority": 1,
  "status": "approved"
}
```

### 4.2 Separated from identity look

| Field | Role |
|---|---|
| `appearance.*` / `prompt_zh` | Structural identity only (no baked smile) |
| `default_expression` | Resting look for candidates / `expr_calm` only |
| `expression_dims[]` | Story-driven emotion dimensions |

### 4.3 Visual profile — generation state only

```json
{
  "expression_dims": {
    "expr_shocked": {
      "files": ["sheet_expr_shocked_….png"],
      "last_generated_at": "…",
      "curated": true,
      "train_include": true
    }
  }
}
```

Visual may **mirror** bible dim ids for UI, but adding/removing dims happens on the bible card (or via a bible API that visual calls).

---

## 5. Derivation Pipeline

### 5.1 Inputs

- Character mentions with `emotion`
- Enriched events with `emotion` + `cast` / participants including this character
- Optional appearance/personality evidence that implies expression (sparingly)

### 5.2 Clustering rules

1. Collect all emotion strings tied to character `id` / name / aliases.
2. Normalize with a small synonym map, e.g.:
   - `震惊|吃惊|骇然` → `shocked`
   - `愤怒|怒|生气` → `angry`
   - `悲伤|哭|哀` → `sad`
   - `关心|温暖|慈祥` → `warm_care`
   - Unmapped phrases → new dim `expr_<slug>` (do not force into the old 8)
3. Merge dims that share the same canonical key; concatenate evidence (cap e.g. 5 quotes).
4. Assign `priority` by frequency × narrative importance (major plot events weight higher if available).
5. Cap dims per character (suggested **4–8** + calm). Overflow stays `proposed` with lower priority for human triage.
6. Re-run is **merge**, not wipe: existing `approved` dims kept; new evidence appended; removed-from-story dims marked `stale` (not auto-deleted).

### 5.3 Framing generation

For each new dim, LLM (or template library) produces a face-only framing string:

- Lead with distinctive mouth / eye / brow cues
- Include Chinese short cue when helpful
- Must not restate wardrobe / full-body identity (those come from appearance locks)

Template library covers known keys; LLM fills unknown keys with the same face-only constraints.

---

## 6. Visual Consumption

### 6.1 Sheet generation

- `group=expression` resolves slots from **bible `expression_dims` where status ∈ {approved, proposed}**, not from global `EXPRESSION_SLOTS`.
- Optional filter: `priority <= N` or explicit `slot_keys`.
- Legacy hardcoded `EXPRESSION_SLOTS` remain as a **fallback library** for framing when a dim maps to a known key; unknown keys use dim.framing.

### 6.2 Trainset check

- Prefer “≥K curated expression dims with evidence” over “≥4 of the fixed 8”.
- Recommended default: **calm + ≥3 story dims** curated.

### 6.3 UI (Visual page)

- List dims from bible for the active character.
- Generate / regenerate **one dim** or **all approved**.
- Show evidence tooltip so QA knows why the slot exists.

---

## 7. API / Stage Hooks (high level)

1. **Normalize / enrich / bible merge** — after emotion-bearing stages, run `build_expression_dims(character, events)` and write into story bible character card.
2. **`POST /projects/{id}/bible/characters/{cid}/expression-dims/rebuild`** — recompute from evidence (merge mode).
3. **`PATCH` dim** — approve / reject / edit framing / priority.
4. **Visual sheets job** — read dims from bible; generate only selected ids.

---

## 8. Migration

1. Keep generating via legacy 8 slots until bible dims exist.
2. Backfill: run clustering once per major character from current enrich data → write `expression_dims`.
3. Map old files `sheet_expr_angry_*` → dim `expr_angry` when id matches.
4. Flip visual default to bible-driven when `expression_dims` non-empty; else fallback to legacy 8.

---

## 9. Success Criteria

- 苏婆婆 (and other majors) only generate expressions justified by story (plus calm).
- Angry / shocked sheets no longer receive resting-smile identity tokens.
- Adding a new volume can add dims without regenerating the whole set.
- Train package lists expression images tagged by dim id + evidence ref (optional in caption metadata).

---

## 10. Open Decisions (defaults proposed)

| Topic | Default |
|---|---|
| Max dims per character | 8 + calm |
| Auto-approve clustered dims | `proposed`; calm auto-`approved` |
| Who edits framing | Bible UI; visual can override locally for one generate only |
| Synonym map language | ZH primary, EN aliases |

---

## 11. Implementation Order (after spec approval)

1. Schema + bible write path for `expression_dims` / `default_expression` (partially started).
2. Clustering from enrich emotions → backfill 青渡川V5 majors.
3. Visual `resolve_sheet_slots` reads bible dims.
4. UI: dim list + single-dim generate.
5. Trainset check + package captions use dim ids.
