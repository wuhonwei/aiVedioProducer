# 分镜脚本（按事件展开 · DeepSeek）— 设计规格

**日期：** 2026-07-15  
**状态：** 已口头确认方案 A，进入实现  
**前置：** 视频就绪 Story Bible（`timeline` 可分镜事件 + 资产卡）

---

## 1. 目标

在 Story Bible 生成之后，以 `timeline[]` 可分镜事件为输入，调用 DeepSeek API 生成逐镜分镜脚本，供后续文生图/视频使用。

### 1.1 已确认

| 项 | 决定 |
|---|---|
| 展开粒度 | 按事件展开（一事件 → 1–N 镜） |
| 架构 | 新阶段 `10_shot_script`（不塞进 Assemble） |
| LLM | DeepSeek官方 API，`deepseek-v4-flash` 默认，可切 `deepseek-v4-pro` |
| Key | `AIVP_DEEPSEEK_API_KEY`（仅 `.env`，不入库） |

### 1.2 非目标

- 真实渲染视频/配音
- 时间轴精剪工具
- 替代 Ollama 文本抽取（仍用本地模型）

---

## 2. 管线

```
… → 09_bible → 10_shot_script
```

产物：

```
stages/10_shot_script/
  shot_script.json      # 全部分镜
  by_event/{event_id}.json   # 可选分文件（实现可选）
```

也可单独从 `10_shot_script` resume；支持 `force_shots=true` 覆盖已有结果。

---

## 3. Shot Schema

```json
{
  "schema_version": 1,
  "generated_at": "...",
  "model": "deepseek-v4-flash",
  "shots": [
    {
      "shot_id": "sh_evt0001_01",
      "event_id": "evt0001",
      "chapter_id": "ch001",
      "order": 1,
      "shot_type": "establishing|wide|medium|closeup|insert|...",
      "camera": "运镜/机位中文描述",
      "action": "画面动作",
      "dialogue": "对白或空串",
      "duration_sec": 3,
      "visual_prompt": "可直贴文生图的中文提示（含角色/地点定妆锚点）",
      "audio_notes": "环境音/对白语气",
      "cast": ["林砚之"],
      "location_name": "青川渡"
    }
  ],
  "warnings": []
}
```

---

## 4. DeepSeek 调用

- Base: `https://api.deepseek.com`（OpenAI Chat Completions）
- `POST /chat/completions`
- `model`: settings
- `response_format: { "type": "json_object" }`
- `thinking: { "type": "disabled" }`（批量分镜优先速度）
- 分批：默认每批 8 个事件；携带关联 major 资产 `prompt_zh` 摘要
- 失败：该批 warnings + 跳过；`shot_strict` 时可失败整步

---

## 5. API / UI

- Job：`force_shots`；`resume_from_step=10_shot_script`
- `GET /api/projects/{id}/shots` 读合并分镜
- 前端「分镜」页：按事件分组卡片；可导出 JSON
- 流水线：「生成分镜」按钮（resume 10 + force）

---

## 6. 测试

- FakeDeepSeek / FakeLlm 固定 shots → coerce + assemble 落盘
- API 启动带 `force_shots` 时 resume=10
- 前端分镜列表渲染冒烟
