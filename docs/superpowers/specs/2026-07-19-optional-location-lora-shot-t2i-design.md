# Optional Location LoRA on Shot T2I

**Date:** 2026-07-19  
**Status:** Implemented  
**Depends on:** `2026-07-19-location-lora-bootstrap-design.md` (multi-LoRA stacking)

## Goal

When generating a shot keyframe image, **location LoRA is opt-in** (default off). Character LoRAs and location text context remain available; only the location LoRA weight stack is gated.

## Non-goals

- Persisting `use_location_lora` on the shot document (per-generation UI/API flag only).
- Full video / I2V pipeline.
- Changing location bootstrap or train flows.
- Forcing location LoRA on character-only probe t2i.

## Decisions (confirmed)

| Topic | Choice |
|-------|--------|
| Default | `use_location_lora=false` |
| Scope | API + ShotsPage「生成镜头图」 |
| Location text | Still inject location trigger / `prompt_zh` when `location_id` is set |
| Location LoRA file | Only stacked when flag is true **and** profile `lora_ready` |
| Persistence | Not stored on shot; checkbox resets to off each visit / generation |

## Behavior

### `generate_shot_with_loras`

New kwarg: `use_location_lora: bool = False`.

| `location_id` | `use_location_lora` | Location text in prompt | Location LoRA in stack |
|---------------|---------------------|-------------------------|------------------------|
| set | `false` | yes (if profile has trigger/prompt_zh) | no |
| set | `true` | yes | yes if `lora_ready` + file |
| unset | ignored | no | no |

Character LoRA stacking unchanged.

Return payload should include `use_location_lora` for debugging / UI.

### API

Extend `POST /api/projects/{project_id}/visual/t2i` (`T2IBody`) so shot generation can use the stack path:

| Field | Type | Default | Notes |
|-------|------|---------|-------|
| `character_id` | `str \| null` | — | Keep for probe / single-char path |
| `character_ids` | `list[str]` | `[]` | Shot cast; preferred when present |
| `location_id` | `str \| null` | `null` | Optional scene |
| `prompt` | `str` | `""` | Usually shot `visual_prompt` |
| `shot_id` | `str \| null` | `null` | Output naming |
| `is_probe` | `bool` | `false` | Existing probe path |
| `use_location_lora` | `bool` | **`false`** | Opt-in location LoRA |

Routing (explicit):

- **Probe / VisualPage path:** `is_probe=true` **or** (`location_id` unset **and** no `character_ids`) → existing `generate_with_character` using `character_id` (required in this path). Location LoRA ignored.
- **Shot keyframe path:** `location_id` set **and/or** non-empty `character_ids` → `generate_shot_with_loras`. Map lone `character_id` into `character_ids` when list empty. Pass `use_location_lora` (default false).

Backward compat: existing VisualPage `visualT2I({ character_id, prompt, is_probe })` keeps working unchanged.

`GET .../visual/lora-refs` location params are out of scope for v1.

### Frontend (ShotsPage)

On the selected shot detail panel:

1. Button **生成镜头图**.
2. Checkbox **使用地点 LoRA** — default **unchecked**.
3. Disabled / helper when shot has no `location_id` or location profile not `lora_ready` (checkbox off + note).
4. Call `visualT2I` with:
   - `shot_id`
   - `location_id` from shot
   - `character_ids` from shot cast (and/or first cast as `character_id` for compat)
   - `prompt` = shot `visual_prompt` (or draft)
   - `use_location_lora` from checkbox
5. Show resulting image (thumb / lightbox) using returned path or a file URL helper if one exists for generations.

No change to VisualPage character probe t2i defaults.

## Tests

- `use_location_lora=False` + ready location → stack has **only** character LoRA(s); location text may still appear in prompt.
- `use_location_lora=True` + ready location → location LoRA first, then characters (existing stack order).
- Default omitted on API body → behaves as false.
- ShotsPage checkbox unchecked by default (if frontend test harness exists; otherwise manual).

## Risks

| Risk | Mitigation |
|------|------------|
| Callers assume old always-on location LoRA | Default false is intentional; docs + return field |
| Prompt still has location trigger without LoRA | Desired; scene words without weight |
| Breaking probe t2i | Keep `generate_with_character` path for probe / simple character_id-only |

## Out of scope follow-ups

- Batch generate all shots with a global toggle.
- Persist preference in project settings.
- `lora-refs` location preview.
