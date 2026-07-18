# Auto Trainset Bootstrap (Character Look-Lock → Curated Set)

**Date:** 2026-07-19  
**Status:** Draft for review  
**Scope:** Project init / post-bible visual bootstrap for **major characters only**. Scene/location LoRA is out of scope (separate track).

## Goal

After story bible + character cards exist, automatically produce a **reviewable character training package** so humans mainly **inspect / swap look-lock / confirm**, not hand-tune prompts or pick every frame.

## Non-goals

- Auto-start LoRA train without human confirm.
- Scene / background / location LoRA (backgrounds stay **plain** for character gens).
- Perfect zero-touch on hard edge cases (elder full-body, masked, etc.) — those end in `needs_review`.

## Principles

1. **One look-lock, many train images** — lock identity; trainset keeps multi-pose / multi-expression diversity.
2. **Character LoRA cares about:** face, wardrobe, pose, expression — **not** scene. Use plain / studio-neutral backgrounds.
3. **Judge before keep** — each generated image is scored; fail → delete → retry with **character-scoped** param tweaks.
4. **Hard caps** — no infinite regenerate loops.
5. **Human gate** — after bootstrap, status `awaiting_confirm`; user can re-pick look-lock and re-expand, then confirm.

---

## Pipeline (per major character)

```text
A. Description QA          prompt_zh + wardrobe vs novel evidence
B. Look-lock candidates    10–20 full-body plain-bg shots
C. Look-lock select        full-body + complete outfit + face/age OK
   └ fail → char-local retune → rebatch B (cap)
D. Set look_lock           keep Top1 as ref; optional Top-K archive
E. Expand trainset         locked candidates (poses) + turnaround + expressions
   └ each image: judge → keep or delete+retry (cap + retune)
F. Package                 curated/ + train_package draft
G. Human review            inspect / swap lock / confirm
```

Frontend shows step progress per character during A–F.

---

## A. Description QA (`prompt_zh` / wardrobe)

**Input:** entity evidence from extract/normalize + current profile fields.  
**Check:** appearance / wardrobe claims are grounded in evidence (or marked inferred).  
**Fail:** rewrite wardrobe / age / distinctive marks with LLM constrained to evidence; re-check.  
**Cap:** e.g. 3 rewrite rounds → `description_needs_review`.  
**Does not invent** novel facts without evidence.

---

## B–C. Look-lock candidate batch + select

### Generation

- Count: **12–16** default (config `bootstrap_lock_candidate_count`, clamp 10–20).
- Framing: **wide full body, head-to-toe, feet/shoes visible**, plain background.
- No look-lock yet (txt2img).
- Strong negatives: half-body, bust, waist-up, busy scenery.

### Judge (must all pass to be lock-eligible)

| Check | Pass rule |
|--------|-----------|
| `framing_full_body` | Head + feet in frame; not waist crop |
| `outfit_complete` | Torso covered; outfit readable; not shirtless / random armor |
| `identity_vs_card` | Age/gender/hair roughly match card |
| `background_plain` | No dominant scenery competing with figure |

**Select:** highest score among lock-eligible.  
**If none eligible:** apply character-local patches (raise framing CFG, strengthen full-body positives/negatives, etc.) → regenerate batch B.  
**Cap:** e.g. 3 lock batches → `look_lock_needs_review` (keep best effort + flag).

**Deletion policy:** non-selected lock-batch images deleted by default (optional keep Top-3 in `look_lock_archive/` for human swap). Prefer archive Top-3 to reduce re-roll cost when human swaps.

---

## D. Look-lock

- Copy winner → `look_lock/ref.png` (+ face crop as today).
- Profile: `look_lock`, `bootstrap_status=expanding`.

---

## E. Expand trainset (still plain background)

From look-lock, generate:

| Slot group | Intent | Diversity |
|------------|--------|-----------|
| Locked candidates | Multi-pose full-body | Mild stance / camera; **same outfit**; plain bg |
| Turnaround | front / side / back | Angle change; outfit lock |
| Expressions | Bible `expression_dims` or defaults | Face crop ref; emotion change |

**Not required for character LoRA:** background variety, location plates (scene LoRA later).

### Per-image judge

Reuse / extend visual judge checks: framing (full-body for non-expr), outfit match to lock, clothing covered, gender, view_angle / expression as applicable.  
**Fail:** delete file → bump character-local retry params → regenerate that slot.  
**Cap:** e.g. 3 tries per slot → leave empty + `slot_failed` warning.

### Character-local param store

Path idea: `visual/characters/{id}/bootstrap_tuning.json` (or profile nested `bootstrap_tuning`).

Mapped from failure tags, examples:

| Failure | Patch |
|---------|--------|
| half_body / cropped_feet | ↑ CFG framing; stronger full-body pos/neg |
| wrong_outfit / shirtless | ↓ denoise (if img2img); outfit_lock_boost |
| wrong_emotion | ↑ expr denoise / CFG |
| identity_drift | ↓ denoise; strengthen face lock |

Patches apply **only to this character’s bootstrap job**, not global QA.

---

## F. Package

- Write keepers into `curated/` with captions (trigger + look + slot tag).
- `train_package.json` draft; `train_status=awaiting_confirm`.
- Do **not** call `execute_lora_train` until confirm.

---

## G. Human review (low touch)

UI:

- Per-character checklist: description QA, look-lock thumb, trainset grid, warnings.
- Actions: **Swap look-lock** (from archive or re-roll lock batch) → optional re-expand; **Confirm**; **Skip character**.
- Goal: human only verifies; defaults should be accept-ready when judges pass.

---

## Init / job model

- Trigger: after majors have profiles (post enrich/assemble), via “初始化视觉训练集” or pipeline flag `bootstrap_trainset`.
- Backend job kind: `visual_bootstrap` (or extend visual job) with `on_progress` including `{character_id, step, done, total, message}`.
- Frontend: progress panel listing characters + current step (requirement 4).

---

## Config knobs (defaults)

| Key | Default |
|-----|---------|
| `bootstrap_lock_candidate_count` | 14 |
| `bootstrap_lock_batch_retries` | 3 |
| `bootstrap_slot_retries` | 3 |
| `bootstrap_desc_rewrite_retries` | 3 |
| `bootstrap_archive_top_k` | 3 |
| `bootstrap_plain_background` | true |

---

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Judge false negatives thrash | Caps + `needs_review`; archive Top-K |
| Wrong description locks bad look | Step A evidence gate |
| GPU time on init | Majors only; sequential per character; progress visible |
| Pose diversity vs outfit lock | Mild actions only; plain bg; denoise band from look-lock lessons |

---

## Success criteria

1. After bootstrap, each major has look-lock **or** clear `needs_review` reason.
2. Curated set has multiple poses/exprs with plain backgrounds; no reliance on scene variety for character LoRA.
3. Human can confirm in one pass or swap lock without manual Comfy params.
4. Progress visible end-to-end on frontend.

---

## Open follow-ups (post-approve)

- Exact judge schema fields / prompts.
- Whether description QA is blocking or soft-warning.
- Scene LoRA bootstrap design (separate spec).
