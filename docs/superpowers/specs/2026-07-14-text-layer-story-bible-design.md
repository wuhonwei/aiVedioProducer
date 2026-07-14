# 文本层 Story Bible 管线 — 设计规格

**日期：** 2026-07-14  
**状态：** 待实现（用户已口头通过设计各节；以本文件为权威规格）  
**范围：** 总蓝图 A–F 中的第一子项目——文本层骨架（含完整 Story Bible 1–16 抽取与可编辑导出）  
**非目标：** 视觉生成、LoRA、LTX 视频、配音、精剪成片（仅在 Bible 中预留/推断字段）

---

## 1. 背景与目标

构建百万字级国风长篇小说的本地 AI 视频生产线。总链路含文本 / 创作 / 视觉 / 视频 / 声音 / 剪辑六层；本规格只交付**文本层**，为后续层提供稳定的 Story Bible 资产。

### 1.1 成功标准（第一期）

1. 上传 TXT 后，批处理流水线可对百万字级输入跑完，或失败后从失败步断点续跑直至成功。
2. 产出结构完整的 Story Bible（字段 1–16 键齐全；部分内容可为空，但不得缺键或静默丢块）。
3. 前端可结构化浏览、基础编辑、版本化导出（JSON + Markdown）。
4. 全程 TDD：阶段/overlay/API 有自动化测试；真实 Ollama 调用为可选 smoke，不阻塞 CI。

### 1.2 已确认约束

| 项 | 决定 |
|---|---|
| 子项目 | A 文本层骨架 |
| LLM | Ollama（本地，5090D） |
| 栈 | Python FastAPI + React/Vite |
| 持久化 | SQLite + 本地文件系统 |
| 架构风格 | 阶段流水线 + 工件落盘（非 Agent 长链路、非重库表 ETL） |
| Story Bible | 1–16 全量抽取 |
| 前端 | 控制台 + 浏览 + 基础编辑 + 导出 |

---

## 2. 系统架构

```
React/Vite UI ──REST──► FastAPI ──► SQLite（项目/任务/overlay 元数据）
                           │
                           ├──► Pipeline Worker（阶段调度）
                           │         └──► LlmClient → Ollama
                           └──► 文件系统（raw / stages / overlays / exports）
```

### 2.1 组件职责

- **UI**：项目列表、源文件上传、任务进度/日志、Story Bible 1–16 浏览与编辑、导出下载、Ollama 健康检查。
- **API**：项目与任务生命周期、Bible 合并读、overlay 写入、导出固化。
- **Worker**：按固定阶段顺序执行；每阶段读写约定路径上的工件；支持 `resume_from_step`。
- **LlmClient**：统一接口；生产实现对接 Ollama；测试使用 FakeLlm。
- **权威产物**：版本化 `story_bible.json`；Markdown 仅为导出视图。

### 2.2 明确不做（本规格）

- 分布式队列 / 多机调度
- 多用户鉴权与权限模型
- 真实图像/视频/音频生成
- Agent 式自由编排（LangGraph 等）作为主路径

---

## 3. 目录与数据流

### 3.1 项目目录

```
data/projects/{project_id}/
  raw/source.txt
  stages/
    01_clean/cleaned.txt
    02_chapters/chapters.json
    03_chunks/chunks.jsonl
    04_extract/{chapter_id}/{chunk_id}.json
    05_normalize/entities.json
    06_timeline/events.json
    07_arcs/arcs.json
    08_bible/story_bible.auto.json
  overlays/story_bible.overlay.json
  exports/
    story_bible.v001.json
    story_bible.v001.md
```

SQLite 存储：`projects`、`jobs`、`job_steps`、以及 overlay 的可选索引元数据；大 JSON 仍以文件为准。

### 3.2 流水线阶段契约

| 步骤 | 名称 | 输入 | 输出 | LLM |
|---|---|---|---|---|
| 01 | Clean | `raw/source.txt` | `cleaned.txt` | 否 |
| 02 | ChapterSplit | cleaned | `chapters.json` | 否（启发式+可配置正则） |
| 03 | Chunk | chapters | `chunks.jsonl` | 否 |
| 04 | Extract | chunks | 每 chunk 一个 JSON | 是 |
| 05 | Normalize | extract 全集 | `entities.json` | 可辅助，默认规则+LLM |
| 06 | Timeline | normalize+extract | `events.json` | 可 |
| 07 | Arcs | timeline+chapters | `arcs.json` | 可 |
| 08 | Assemble | 上述全部 | `story_bible.auto.json` | 可（汇总补全） |
| — | MergeView | auto ⊕ overlay | 导出 JSON/MD | 否 |

**进度：** `当前阶段` + `完成 chunk / 总 chunk`。  
**状态机：** `queued → running → (step_failed \| paused) → running → succeeded`；支持从指定步续跑。

---

## 4. Story Bible 字段（1–16）

组装与导出必须包含以下顶层键（名称可在实现中用稳定英文 snake_case，但语义一一对应；导出 Markdown 使用中文标题）：

1. **项目元信息** — `project_meta`
2. **故事一句话概括** — `logline`
3. **世界观设定** — `worldbuilding`
4. **主线剧情 / 篇章结构** — `plot_structure`
5. **主要角色 Bible** — `characters`
6. **角色关系** — `character_relations`
7. **地点 / 场景 Bible** — `locations`
8. **组织 / 阵营 / 势力** — `factions`
9. **重要道具 / 法宝 / 物件** — `props`
10. **事件时间线** — `timeline`
11. **伏笔 / 悬念 / 回收** — `foreshadowing`
12. **影视化改编信息** — `adaptation_notes`
13. **视觉风格 Bible** — `visual_style`
14. **角色视觉设定** — `character_visuals`
15. **声音设定 Voice Bible** — `voice_bible`
16. **分镜/资产生产约束** — `production_constraints`

另附：`warnings[]`（缺失块、跳过坏 chunk、低置信字段等）、`schema_version`、`generated_at`、`source_stats`。

字段 12–16 在文本层由抽取/汇总**推断填写**；证据不足时填空结构 + warning，不得省略键。

---

## 5. API 与编辑模型

### 5.1 REST 端点

- `POST /api/projects` · `GET /api/projects` · `GET /api/projects/{id}`
- `POST /api/projects/{id}/source` — 上传 TXT
- `POST /api/projects/{id}/jobs` — 启动；body 可含 `resume_from_step`
- `GET /api/projects/{id}/jobs/{job_id}` — 状态与进度
- `GET /api/projects/{id}/bible` — 合并视图（auto ⊕ overlay）
- `PATCH /api/projects/{id}/bible` — JSON Merge Patch 写入 overlay
- `POST /api/projects/{id}/exports` — 固化版本，返回下载信息
- `GET /api/health/ollama` — 模型可用性

错误体统一：`{ "code", "message", "details"? }`。

### 5.2 前端信息架构

- 项目列表 / 新建
- 项目内：概览 | 流水线 | Story Bible | 导出
- 设置：Ollama base URL、模型名
- Story Bible：左侧 1–16 目录，右侧表单编辑；保存进 overlay
- 支持「重置某字段到自动结果」（删除 overlay 对应路径）

### 5.3 Overlay 规则

- 浏览始终看合并视图。
- 保存只更新 `story_bible.overlay.json`。
- 导出冻结到 `exports/story_bible.vNNN.*`，不受后续重跑自动改写。
- 重跑流水线**默认保留** overlay；仅当用户显式选择「丢弃人工修改」时清空。

---

## 6. 错误处理

| 类型 | 策略 |
|---|---|
| Ollama 超时/连接失败 | 指数退避重试；记入 `job_steps`；超限 → `step_failed` |
| 编码无法识别 / 切章结果为空 | 不可重试，立即失败并给可读原因 |
| LLM JSON 不合 schema | 同 chunk 再试 1–2 次（约束 + repair）；仍失败则标记错误；可配置「跳过坏块继续」 |
| 部分 chunk 缺失 | 组装填空/`null`，写入 `warnings[]`，禁止静默丢弃 |
| API/前端 | 展示失败 step 与日志尾部；支持续跑 |

---

## 7. TDD 与测试策略

**合入规则：** 新阶段或端点必须先写失败测试 → 实现 → 绿灯；禁止无测试合入核心逻辑。

1. **纯阶段单测（pytest）：** Clean / ChapterSplit / Chunk，夹具 TXT，无 LLM。
2. **抽取契约：** FakeLlm 固定响应 → schema、归一化、稳定 ID。
3. **组装：** stages 金样 → 完整 1–16 `story_bible.auto.json`。
4. **Overlay：** Merge Patch、重置路径、重跑保留 overlay。
5. **API：** httpx TestClient + 临时目录 + 测试用 SQLite。
6. **金样回归：** 小号国风样章全链路（FakeLlm）快照锁定。
7. **前端：** Vitest + Testing Library 覆盖上传触发、进度展示、Bible 保存。
8. **可选：** 真实 Ollama smoke（本地/手动），不进默认 CI 门禁。

---

## 8. 仓库布局（建议）

```
backend/          # FastAPI、pipeline、LLM、SQLite
frontend/         # React/Vite
data/projects/    # 运行时数据（gitignore）
docs/superpowers/ # 规格与计划
tests/            # 或 backend/tests + frontend 内测
```

包管理：backend 用 `uv` 或 `pip` + `pyproject.toml`；frontend 用 `pnpm` 或 `npm`。具体在实现计划中锁定。

---

## 9. 与总蓝图的关系

本规格交付物（版本化 Story Bible）是创作层（剧本/分镜）、视觉层、声音层的上游输入。后续子项目不得破坏 1–16 schema 的向后兼容（`schema_version` 递增时需迁移说明）。

---

## 10. 开放实现细节（计划阶段锁定，不阻塞本规格）

- Ollama 默认模型名与 context 长度配置项
- chunk 目标字数与重叠策略的具体默认值
- Worker 是 API 同进程后台任务还是独立进程（首期允许同机单 worker）
- Normalize 阶段规则优先 vs LLM 优先的精确配比

以上细节不得改变第 2–7 节的架构与契约。
