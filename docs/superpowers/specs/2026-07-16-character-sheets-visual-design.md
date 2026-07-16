# Character sheets + stronger portrait t2i

## Goal

Fix character 试生成 producing empty palace scenes; add turnaround + expression sheets; add image zoom and delete on Visual page.

## Prompt / Comfy

- Default probe framing: `solo, 1person, looking at viewer, upper body portrait, simple background, 人物半身特写`
- Shared character negative includes: scenery, palace, architecture, no humans, empty, landscape
- Character gens use **768×1024**
- If profile has a LoRA filename, Comfy workflow inserts `LoraLoader` (strength ~0.75)

## Sheets

`POST .../visual/sheets` job (same polling as candidates) writes under `visual/characters/{id}/sheets/`:

| File | Content |
|------|---------|
| turnaround front/side/back | full body, simple/white bg |
| expr: 平静、微笑、开心、疑惑、愤怒、悲伤、惊讶、害羞 | face close-up |

## UI

- Button「生成角色表」
- Click image → lightbox zoom
- Delete on candidates / generations / sheets (`DELETE .../files/{folder}/{filename}`)

## Out of scope

- Real LoRA training (still package export)
- Video / I2V
