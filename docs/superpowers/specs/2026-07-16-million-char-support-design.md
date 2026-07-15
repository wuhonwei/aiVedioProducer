# 百万字小说单机支持（方案 A）设计

**日期:** 2026-07-16  
**状态:** 已实施（单机 FastAPI，不引入 Redis/Celery）

## Goal

约 100 万字长篇可过夜稳定跑通：可中断续跑；后期剧情不因硬截断丢失；前端可分页翻阅时间线与分镜。

## Architecture

- 进程内 Job + SQLite（既有模型）
- 文本层增加 **卷（volume）** 一等公民：`stages/00_volumes/volumes.json`
- 切卷规则：累计正文约 **8 万字/卷** 或 **40 章/卷**（先触发者）
- 抽取：`ThreadPoolExecutor`，默认 `AIVP_EXTRACT_WORKERS=4`；进度每 10 chunk 或 5s 才 commit
- 归一：每卷 normalize → `merge_volume_entities`（首字/长度分桶模糊配对）
- Enrich：事件滑窗（默认窗口 40）
- Bible：先写 `volume_synopses.json`，再合成 logline/worldbuilding；`timeline` 仅预览 + `timeline_ref`
- 分镜：按卷写 `shot_script.{vol}.json` + `shot_script.index.json`
- API：`GET .../timeline?offset&limit`，`GET .../shots?offset&limit&event_id`

## Out of scope

Redis/Celery、跨机多 GPU、MinIO、视频层百万镜头量产。
