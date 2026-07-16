# Full-body character look dimensions for prompt_zh

## Problem

Male majors often render as women because `prompt_zh` omitted hard gender/body/face parts; Guofeng priors favor female.

## Required dimensions (every major)

| Dimension | Field |
|-----------|--------|
| 性别 | `gender_presentation` → 男性/女性 in prompt |
| 年龄 | `age_look` |
| 身材 | `appearance.body` |
| 身高 | `appearance.height` |
| 四肢 | `appearance.limbs` |
| 体重 | `appearance.weight` |
| 脸型 | `appearance.face_shape` |
| 眼睛 | `appearance.eyes` |
| 鼻子 | `appearance.nose` |
| 眉毛 | `appearance.eyebrows` |
| 嘴 | `appearance.mouth` |
| 头发 | `appearance.hair` (length + color + style) |
| 特征 | `appearance.distinctive_marks` |

`appearance.face` kept as a short summary for legacy signature / UI.

## Prompt assembly

`compose_character_prompt_zh` rebuilds `prompt_zh` at end of `ensure_character_card` for majors (LLM cannot skip dimensions).

Gender-aware negative appended in visual gens: male → ban `1girl, woman`; female → ban `1boy, man`.

## Migration

Re-run enrich (force) on existing projects so bible/profile `prompt_zh` refresh.
