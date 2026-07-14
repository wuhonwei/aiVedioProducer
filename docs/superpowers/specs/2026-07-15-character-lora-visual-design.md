# 角色 LoRA 视觉层（ComfyUI）— 设计规格

**日期：** 2026-07-15  
**状态：** 方案 A 已确认，进入实现  
**前置：** 视频就绪 Story Bible（major 角色 + `prompt_zh` / 定妆字段）+ 分镜脚本

---

## 1. 目标

对 Story Bible 中 `tier: major` 角色：

1. 用底模 + 定妆 prompt **自动生成候选参考图**  
2. 人工筛选训练集  
3. **LoRA 微调**，绑定稳定 trigger  
4. 文生图时按角色名加载对应 LoRA，保证形象一致  

### 1.1 已确认

| 项 | 决定 |
|---|---|
| 底座 | ComfyUI + SDXL / 国风二次元 checkpoint + LoRA |
| 训练集来源 | 自动出候选 → 人工筛选（本期不上手动上传） |
| 覆盖角色 | 仅 `tier: major` |
| 架构 | AIVP 编排 + kohya/sd-scripts 训练 + ComfyUI API 推理 |

### 1.2 非目标（本期）

- 地点/道具 LoRA（可后续）  
- 视频生成 / ControlNet 分镜对齐（后续）  
- 云端训练  

---

## 2. 目录

```
data/projects/{id}/visual/
  characters/{character_id}/
    profile.json          # trigger、状态、base_model
    candidates/           # 自动生成待选
    curated/              # 勾选通过的训练图 + captions
    lora/                 # 输出 .safetensors
  comfy/
    workflows/            # 候选图 / 推理工作流模板
  jobs/                   # 训练/生成任务日志
```

---

## 3. 阶段与 Job

不塞进文本 STAGE_ORDER；独立视觉任务类型：

| job_type | 说明 |
|---|---|
| `visual_candidates` | 为指定 major 角色批量出候选图 |
| `visual_lora_train` | 用 curated 训 LoRA |
| `visual_t2i` | 用角色 LoRA + prompt 出图（可挂分镜 visual_prompt） |

状态：`queued/running/succeeded/failed/cancelled`（复用 Job 表或扩展 `job_kind` 字段）。

实现优先：**扩展现有 Job** 增加可选 `job_kind`（默认 `text_pipeline`），避免第二套调度。

---

## 4. Trigger 约定

- `trigger = slug(name) + "_aivp"`，如 `linyanzhi_aivp`  
- caption 模板：`{trigger}, {prompt_zh 摘要}, guofeng anime character sheet`  
- 生成时 prompt 必须包含 trigger，Comfy 工作流 LoRA 强度默认 0.7–0.85  

---

## 5. ComfyUI / 训练配置（Settings）

```
AIVP_COMFY_BASE_URL=http://127.0.0.1:8188
AIVP_COMFY_CHECKPOINT=...          # 或由 UI/工作流固定
AIVP_LORA_TRAIN_CMD=...            # kohya/sd-scripts 入口，可选
AIVP_LORA_OUTPUT_ROOT=...          # 默认项目 visual 下
```

无 ComfyUI 时：候选生成任务失败并给可读错误；单测用 FakeComfy。

---

## 6. API

- `GET /projects/{id}/visual/characters` — major 角色 + 状态（candidates/curated/lora）  
- `POST /projects/{id}/visual/candidates` — body: `{ character_ids?: [] }`  
- `POST /projects/{id}/visual/characters/{cid}/curate` — body: `{ keep: ["file.png", ...] }`  
- `POST /projects/{id}/visual/lora/train` — body: `{ character_ids?: [] }`  
- `POST /projects/{id}/visual/t2i` — body: `{ character_id, prompt, shot_id? }`  
- `GET /projects/{id}/visual/characters/{cid}/images/...` — 静态图（或 FileResponse）

---

## 7. 前端

新页「角色视觉」：

1. 列表：major 角色、候选数、已选、LoRA 是否就绪  
2. 「生成候选」→ 刷新缩略图 → 勾选 → 「确认训练集」  
3. 「训练 LoRA」进度  
4. 「试生成」：输入 prompt / 选用分镜 visual_prompt  

---

## 8. 验收

1. 《青渡川》major 角色可出 ≥8 张候选（Comfy 可用时）  
2. 筛选后 curated 有 caption  
3. 训练产物 `.safetensors` 落盘（训练器可用时）  
4. 同 trigger 两次试生成面孔显著一致（人工目检）  
5. FakeComfy 下 API/编排单测绿灯  

---

## 9. 实现顺序

1. paths + character profile + FakeComfy 候选生成  
2. curate API + 前端勾选  
3. LoRA train 包装（检测外部脚本；否则生成可运行配置包）  
4. Comfy 推理工作流挂 LoRA  
5. 与分镜页「用此镜试生成」入口  
