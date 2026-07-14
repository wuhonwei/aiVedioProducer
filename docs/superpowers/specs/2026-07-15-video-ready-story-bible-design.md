# 视频就绪 Story Bible（资产补全 + 可分镜事件）— 设计规格

**日期：** 2026-07-15  
**状态：** 待用户审阅规格文件后进入实现计划  
**前置：** `2026-07-14-text-layer-story-bible-design.md`（文本层骨架已交付）  
**范围：** 将 Story Bible 1–16 从「实体名册」升级为下游图像/视频可消费的中间件  
**非目标：** 逐镜头 `shot_list` 生成器、真实文生图/视频调用、配音合成

---

## 1. 背景与目标

现有流水线已能跑通并产出键齐全的 Story Bible，但对视频生产仍偏薄：角色/地点/道具多为 `name + aliases`；`character_visuals` / `voice_bible.cast` 常空；timeline 仅短摘要；势力常空。实测《青渡川》证明「任务成功 ≠ 可拍」。

### 1.1 已确认决策

| 项 | 决定 |
|---|---|
| 完整资产覆盖 | 角色、地点、道具、势力四类 |
| 缺证据策略 | 先写原文 `evidence`，再推断补齐，并记录 `inferred_fields` |
| 覆盖粒度 | 仅**主干实体**写完整卡；非主干 `tier: minor` + 一行 `brief` |
| 架构 | Normalize 后新增 **Enrich** 阶段（非加厚每 chunk 抽取、非仅 Assemble 一次综合） |
| 本轮交付深度 | 完整资产卡 + **可分镜事件**（cast / visual_beat / camera_hint）+ 写满 visual/voice/production；**不做**完整分镜头表 |

### 1.2 成功标准

以《青渡川》端到端（Ollama 可选 smoke）验收：

1. 主干角色定妆相关字段非空，且含 `prompt_zh`、`consistency_anchors`。
2. 主干地点「青川渡」、主干道具「玉佩」含可用 `prompt_zh`。
3. timeline 中至少 **70%** 事件含 `cast` 与 `visual_beat`。
4. `character_visuals` 与 `voice_bible.cast` 对主干角色非空。
5. `visual_style` 含稳定画风锚点（不止散乱 keywords）；`production_constraints` 含同场人数与禁元素等可执行约束。
6. 若原文无明确势力：可推断 0–1 个并 `inferred`，或写入 `warnings`；键不得缺失。
7. FakeLlm 单测覆盖 majors 选择、enrich coerce、assemble 映射；真实 Ollama 不阻塞 CI。

---

## 2. 管线变更

### 2.1 阶段顺序（顺延编号）

```
01_clean → 02_chapters → 03_chunks → 04_extract
→ 05_normalize
→ 06_enrich_assets          # 新增
→ 07_timeline               # 原 06；输入可含 enrich 旁路
→ 08_arcs                   # 原 07
→ 09_bible                  # 原 08；消费 assets + 可分镜事件
```

`STAGE_ORDER`、路径、`resume_from_step`、UI 进度文案同步更新。旧项目从 `06_enrich_assets` 或之后续跑时，若缺新工件则从该步重做。

### 2.2 新目录产物

```
data/projects/{id}/stages/06_enrich_assets/
  majors.json      # 主干名单、分数、理由
  assets.json      # 四类完整/简档资产卡
  events_enriched.json   # 可分镜事件（供 timeline/assemble）
```

### 2.3 Enrich 内部步骤

1. **select_majors**（规则，默认可无 LLM）  
   打分信号：实体在 extracts 出现次数、timeline/未来 arcs 摘要提及、是否在章节标题中出现。  
   默认 TopN（可配置）：角色 8、地点 8、道具 6、势力 4。

2. **enrich_batches**（LLM）  
   按类型分批：角色一批、地点一批、道具一批、势力一批（过长则再切批）。  
   输入：实体名/别名、相关事件摘要列表、原文证据片段（从 chunk 检索共现句，截断）。  
   输出：完整资产卡；策略 B（证据优先）。

3. **enrich_events**（LLM，可批）  
   对事件列表（可先取每章高分/前 N）补齐可分镜字段。  
   输出写入 `events_enriched.json`；`07_timeline` 优先合并该文件，或由 assemble 直接读取。

**失败策略：** 单批失败 → `warnings` + 该实体降级 `brief`；默认不阻断后续。配置 `enrich_strict=true` 时整步 `step_failed`。  
**续跑：** 已有资产卡默认跳过；API/任务参数支持 `force_enrich=true` 强制重写。

---

## 3. 数据 Schema

### 3.1 共用元字段

所有资产卡包含：

- `id`, `name`, `aliases[]`, `tier`: `"major" | "minor"`
- `evidence[]`, `inferred_fields[]`
- `prompt_zh`（可直贴文生图/视频提示的中文段落）
- minor 额外：`brief`（一句话）；major 写满下列专用字段

### 3.2 角色（major）

```
role, age_look, gender_presentation
appearance: { face, hair, body, distinctive_marks }
wardrobe: { default, alternate[], colors[] }
temperament[], signature_actions[]
voice: { timbre, pace, pitch, speech_habits[] }
consistency_anchors[]
```

### 3.3 地点（major）

```
era_mood, time_of_day_default, weather_default
palette[], materials[], camera_grammar, establishing_shot
```

### 3.4 道具（major）

```
scale, material, motifs[], closeup_notes, symbolism
```

### 3.5 势力（major）

```
goal, emblem, uniform_palette[], behavior_rules[], visual_signature
```

### 3.6 可分镜事件（非完整分镜头表）

```
id, chapter_id, summary
cast[]            # character id 或稳定 name
location_id?
props[]
dramatic_beat     # hook|turn|climax|resolution|…
emotion
visual_beat       # 一句话画面
camera_hint       # 景别/运镜建议
duration_hint_sec
```

---

## 4. Assemble → Bible 1–16 映射

| Bible 键 | 来源 |
|---|---|
| 5 characters / 7 locations / 8 factions / 9 props | `assets.json`（major 完整，minor brief） |
| 6 character_relations | LLM/规则：共现事件 + 资产角色 |
| 10 timeline | `events_enriched` 优先，否则旧 events 降级 |
| 11 foreshadowing / 12 adaptation_notes | 保持抽取合并；adaptation 可附「主干场景拍摄提示」 |
| 13 visual_style | 由地点 palette + 角色色板 + visual cues 汇总 **style_anchors** |
| 14 character_visuals | 自角色资产投影（定妆摘要，非空 notes） |
| 15 voice_bible | `cues` 保留；`cast[]` 自角色 `voice` |
| 16 production_constraints | `max_chars_on_screen`、禁元素、一致性锚点清单、时长提示聚合 |
| 2–4 logline / worldbuilding / plot_structure | 现有 synth，上下文改为富资产摘要 |

`schema_version` 升为 `2`；`source_stats.video_ready = true`。旧 overlay 按键合并仍有效；未知嵌套字段以 overlay 覆盖为准。

---

## 5. API / 前端影响（最小）

- Job 启动可选：`force_enrich`, `resume_from_step` 含 `06_enrich_assets`。
- Bible 浏览仍按 1–16；右侧 JSON/文本需能展示嵌套资产字段（现有 textarea 足够，本轮不强制表单化）。
- 进度：Enrich 阶段写入 Job 的 `chunks_done / chunks_total` 为「已完成 enrich 批 / 总批」（与 extract 阶段复用同一进度字段，UI 无需新控件；阶段名区分含义）。

---

## 6. 测试策略

1. **select_majors：** 固定 extracts/events → TopN 稳定。  
2. **coerce enrich：** messy LLM JSON → 合法资产卡（沿用 coerce 模式）。  
3. **assemble：** Fake 资产 + 可分镜事件 → 14/15/16 非空；characters 含 appearance。  
4. **runner：** FakeLlm 金样全链路含 `06_enrich_assets`。  
5. **可选：** `docs/novels/青渡川.txt` Ollama smoke 对照成功标准 1–6。

---

## 7. 风险与边界

- 推断外貌可能与读者想象不符 → 必须 `inferred_fields` + overlay 可改。  
- 百万字 TopN 过小会漏重要配角 → TopN 与权重可配置。  
- Enrich 增加墙钟时间 → 分批 + 跳过已有卡；默认不进「每 chunk 全量外貌」。  
- 本规格**明确不做**逐镜 `shot_list`；`camera_hint` 仅为建议级字段。

---

## 8. 实现顺序（供后续计划拆分）

1. 阶段重编号 + paths + majors 空壳与 majors 规则  
2. 资产/事件 schema + coerce + FakeLlm 测试  
3. enrich_batches / enrich_events + runner 接线  
4. assemble 映射与 Bible v2 字段填充  
5. API/进度字段 + 青渡川 smoke 清单  

---

## 9. 决议记录

- 资产类型：ABCD 全要  
- 填充策略：B 证据优先再推断  
- 覆盖：A 仅主干完整卡  
- 实现路径：A 新增 Enrich 阶段  
- 优化范围：A 资产 + 可分镜事件 + visual/voice/production（无完整分镜表）  
- 设计节 1–3：用户已口头确认
