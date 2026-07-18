# Location LoRA Bootstrap（Major 地点空镜定妆 → 训练集）

**Date:** 2026-07-19  
**Status:** Approved for planning  
**Scope:** Per-project **major locations only**, isolated under each story’s `visual/locations/`. Genre-wide reusable scene packs are out of scope.

## Goal

After story bible location cards exist, automatically produce a **reviewable empty-scene training package** per major location so humans mainly **inspect / swap establishing lock / confirm**, then optionally train a location LoRA. At shot t2i time, **stack location LoRA + character LoRAs**.

## Non-goals

- Cross-project / genre-common scene packs (客栈/竹林通用包).
- Auto-start LoRA train without human confirm.
- Baking characters into scene LoRA (training images are **empty plates** only).
- Merging character + location into a single `visual/assets` abstraction (future optional refactor).

## Decisions (confirmed)

| Topic | Choice |
|-------|--------|
| Scope | Per-story major locations, project-isolated |
| Train images | Pure empty scenes (no readable people) |
| Pipeline depth | Align with character bootstrap (QA → lock → expand → confirm) |
| Architecture | Parallel tree `visual/locations/{id}/` (not unified asset refactor) |

## Principles

1. **One establishing lock, many env plates** — lock place identity; trainset keeps angle / TOD / weather / material diversity.
2. **Scene LoRA cares about:** architecture, materials, palette, light, spatial layout — **not** faces or wardrobe.
3. **Judge before keep** — fail → delete → character-local-style **location-local** retune (caps).
4. **Hard caps** — no infinite regenerate loops.
5. **Human gate** — `awaiting_confirm` before package/train; no auto train.
6. **Isolation** — separate directories, jobs, triggers from character LoRA; never use character look-lock as location img2img base.

---

## Directory layout

```text
data/projects/{project_id}/visual/locations/{location_id}/
  profile.json
  candidates/
  look_lock/                 # establishing ref.png (+ optional crops)
  look_lock_archive/         # Top-K alternates for human swap
  sheets/                    # multi-angle / TOD / weather / material plates
  curated/
  bootstrap_tuning.json
  lora/
```

**Trigger:** `slug(name)_loc_aivp` (distinct from character `*_aivp`).

**Profile fields (minimum):** `location_id`, `name`, `trigger`, `prompt_zh`, palette/materials/era mirrors from bible card, `look_lock`, `bootstrap_status`, `train_status`, `bootstrap_warnings`.

---

## Pipeline (per major location)

```text
A. Description QA          prompt_zh / palette / materials vs evidence
B. Establishing candidates 10–20 empty wide plates
C. Lock select             no_people + place_readable + env framing
   └ fail → location-local retune → rebatch B (cap)
D. Set look_lock           Top1 ref; archive Top-K
E. Expand trainset         angles / TOD / weather / materials (still empty)
   └ per image: judge → keep or delete+retry (cap)
F. Package                 curated/ + captions with trigger
G. Human review            inspect / swap lock / confirm / skip
```

### A. Description QA

- Ground claims in location evidence / bible card.
- Cap rewrite rounds (default 3) → `description_needs_review`.
- Mark `inferred_fields` when guessing.

### B–C. Establishing batch + select

**Generation**

- Count: config `location_bootstrap_lock_count` default 14 (clamp 10–20).
- Framing: wide establishing / environment; place-dominant.
- Strong negatives: person, face, portrait, character sheet, crowd, close-up face.
- Phase B: txt2img (no location lock yet).

**Judge (all must pass for lock-eligible)**

| Check | Pass rule |
|-------|-----------|
| `no_people` | No readable face / clear human body |
| `place_readable` | Recognizable as this place type / card |
| `establishing_or_env` | Environment-led; not random texture / prop macro only |
| `style_match` | Palette / materials / era roughly match card |
| `not_character_sheet` | Reject full-body portrait-style framing |

Select highest score among eligible. If none: apply `bootstrap_tuning` patches → rebatch. Cap: `location_bootstrap_lock_batch_retries` (default 3) → `look_lock_needs_review`.

**Deletion:** non-selected lock-batch deleted by default; keep Top-K in `look_lock_archive/`.

### D. Look-lock

- Winner → `look_lock/ref.png`.
- Profile: `look_lock`, `bootstrap_status=expanding`.

### E. Expand (empty only)

From look-lock (light img2img OK to preserve structure):

| Slot group | Intent |
|------------|--------|
| Locked candidates | Mild camera / depth changes; same place |
| Angle plates | front / three-quarter / side / reverse establishing |
| TOD / weather | dawn / dusk / fog / light rain (card defaults first) |
| Material close-ups | stone / wood / water / mist textures that belong to the place |

Per-image judge; fail → delete + location-local retry. Cap: `location_bootstrap_slot_retries` (default 3).

### F–G. Package + human

- Curated captions: `{trigger}, {prompt_zh summary}, empty scene, no people, guofeng location plate`.
- `train_status=awaiting_confirm`; **do not** call train until confirm.
- UI actions: swap lock from archive, confirm, skip.

---

## Location-local tuning

Path: `visual/locations/{id}/bootstrap_tuning.json`.

Example failure → patch mapping:

| Failure | Patch |
|---------|--------|
| `has_people` / `face_detected` | Stronger empty negatives; ↑ CFG for scenery |
| `place_unreadable` | Boost card materials/palette tokens; ↑ denoise carefully if img2img |
| `busy_wrong_place` | Extra negative for competing landmarks |
| `too_tight_crop` | Force wide establishing positives |

Patches apply **only to this location’s bootstrap**, not global QA / character tuning.

---

## API

| Endpoint | Role |
|----------|------|
| `GET .../visual/locations` | List major locations + status |
| `POST .../visual/locations/bootstrap` | Job `visual_location_bootstrap` |
| `GET .../visual/jobs/{id}` | Progress: `location_id`, `bootstrap_step`, `progress_note` |
| `POST .../visual/locations/{id}/bootstrap/confirm` | → `curated_ready` |
| `POST .../visual/locations/{id}/bootstrap/skip` | Skip |
| `POST .../visual/locations/{id}/bootstrap/swap-look-lock` | Archive / candidates swap |
| Look-lock / curate / package / train | Location-scoped mirrors of character routes (train only after confirm) |

Stub backend: skip real vision judge (heuristic pass) like character bootstrap tests.

---

## Frontend

- Visual page: **角色 | 地点** tab (or dual nav).
- 「初始化地点训练集」+ progress per location/step.
- Review panel: establishing thumb, archive swap, warnings, confirm / skip.
- No auto LoRA train after confirm.

---

## Shot t2i stacking

1. Resolve `location_id` + cast character ids from shot.
2. Load location LoRA if `lora_ready`; load each character LoRA if ready.
3. Prompt shape: `{loc_trigger}, {loc env summary}, {char_triggers}, {action}, {shot visual_prompt}`.
4. Default strengths: location `0.7` (`location_lora_strength`), characters `0.7–0.85`.
5. When location LoRA active, do **not** force character-style plain-background negatives that wipe the scene.

---

## Config knobs (defaults)

| Key | Default |
|-----|---------|
| `location_bootstrap_lock_count` | 14 |
| `location_bootstrap_lock_batch_retries` | 3 |
| `location_bootstrap_slot_retries` | 3 |
| `location_bootstrap_desc_rewrite_retries` | 3 |
| `location_bootstrap_archive_top_k` | 3 |
| `location_lora_strength` | 0.7 |

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| People leak into trainset | Hard `no_people` judge + strong negatives + delete |
| Location LoRA fights character LoRA | Separate triggers; tune strengths; prompt order loc→char |
| Empty plates look generic | Lock on establishing; evidence-grounded prompt_zh; material slots |
| GPU time | Majors only; sequential per location; visible progress |

---

## Success criteria

1. Each major location has establishing look-lock **or** clear `needs_review`.
2. Curated set is multi-view / multi-TOD **empty** plates; projects do not share location files.
3. Human can confirm or swap lock without hand-tuning Comfy.
4. After train, shot t2i can stack location + character LoRAs.

---

## Follow-ups (explicitly later)

- Genre-common scene packs.
- Unified `visual/assets/{kind}` refactor.
- ControlNet / depth for shot camera match.
