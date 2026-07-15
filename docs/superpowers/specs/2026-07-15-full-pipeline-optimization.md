# AI Video Producer 全链路优化规格

> 状态：Active（实施 Phase 0～3）  
> 创建：2026-07-15  
> 仓库：`aiVedioProducer`

## 目标

将项目从文本层 MVP 升级为可控、可审核、可复现的单机 AI 视频生产工作台。近期交付：

```text
真实小说片段
  → 带报告 / offset / evidence 的结构化数据
  → 可审核 Story Bible
  → 生产级分镜 + asset_plan
```

## 阶段总览

| 阶段 | 目标 | 本轮 |
|------|------|------|
| Phase 0 | 工程基线、文档、跨平台启动 | 实施 |
| Phase 1 | 清洗/章节/chunk/抽取/归一可靠性 | 实施 |
| Phase 2 | Story Bible 审核与版本化 | 实施 |
| Phase 3 | 分镜 YAML + asset_plan | 实施 |
| Phase 4 | 角色视觉与 LoRA 闭环 | 入档延期 |
| Phase 5 | 关键帧与 I2V 候选 | 入档延期 |
| Phase 6 | 音频、Timeline、成片 | 入档延期 |

## Phase 0～3 验收要点

- 清洗写出 `metadata.json` / `clean_report.json`
- 章节可识别常见网文标题并带 offset + `chapter_report.json`
- chunk 默认 4000/500，带 offset 与前后链 + `chunk_report.json`
- 抽取关键事实带 evidence；写出 `extract_report.json` / `errors.json`
- 归一输出 uncertain / merge_history；可审核 API
- Bible 持久化 merged + meta；区块 review/lock
- Shot schema v2 + YAML 导出 + asset_plan

## 原则

1. 先结构化，再创作  
2. 关键事实可回链 evidence / offset  
3. 人工介入产品化（审核、锁定、候选选择）  
4. 生成任务可复现（参数与输出路径记录）  
5. 短期不微服务化  

详细任务拆解见：`docs/superpowers/plans/2026-07-15-phase0-3-optimization.md`
