# AI Video Producer（AIVP）

将长篇小说加工为结构化 **Story Bible**、生产级分镜与资产计划，面向后续国风二次元视频生产。当前主分支为 **`master`**。

## 能力矩阵

**已支持**

- 文本层结构化流水线（清洗 → 章节 → chunk → 抽取 → 归一 → enrich → timeline → arcs → Bible）
- Story Bible 自动生成 + overlay 人工编辑与导出
- 分镜初步生成（DeepSeek / 启发式回退）
- 角色视觉候选图 stub、LoRA 训练包生成
- 本仓库专用 ComfyUI（`tools/ComfyUI`，端口 8190）文生图 API
- 项目 / 流水线 / Bible / 分镜 / 角色视觉 / 导出 / 设置控制台

**尚未支持（Phase 4～6）**

- LTX / 其他 I2V 视频生成
- TTS 音频
- FFmpeg 成片

## 环境要求

- **Python 3.12+**
- **Node.js 18+**
- **Ollama**（可选）：默认 `http://127.0.0.1:11434`，模型 `qwen2.5:14b`
- **DeepSeek API**（可选）：分镜生成；未配置时使用启发式回退
- **本项目 ComfyUI**（试生成 / 真图）：独立安装，**不要**共用其它项目的 8188 实例。见 `scripts/setup-comfy.md`，启动：`.\scripts\start-comfy.ps1`（`http://127.0.0.1:8190`）

## 环境检查

```bash
# macOS / Linux
./scripts/check-env.sh

# Windows PowerShell
.\scripts\check-env.ps1
```

## 一键启动

**Windows**

- 双击 `start-dev.bat`，或：

```powershell
.\scripts\start-dev.ps1
```

**macOS / Linux**

```bash
chmod +x scripts/*.sh
./scripts/start-dev.sh
```

也可用 Make：

```bash
make install
make check-env
make dev-backend   # 终端 1
make dev-frontend  # 终端 2
```

后端 `http://127.0.0.1:8000`，前端 `http://127.0.0.1:5173`。

## 后端

```bash
cd backend
pip install -e ".[dev]"
cp .env.example .env   # 可选
uvicorn aivp.api.app:create_app --factory --reload --port 8000
```

## 前端

```bash
cd frontend
npm ci
npm run dev
```

`/api` 经 Vite 代理到后端 8000。

## 测试

```bash
# 后端
cd backend && python -m pytest -v
# 或
make test-backend

# 前端
cd frontend && npm test
# 或
make test-frontend

make test   # 两者
```

## 目录概览

| 路径 | 说明 |
|------|------|
| `backend/src/aivp/` | 流水线、API、Bible、视觉模块 |
| `frontend/src/` | React 控制台 |
| `backend/data/` | 运行时项目数据（`AIVP_DATA_ROOT`） |
| `docs/superpowers/` | 规格与实施计划 |

## 相关文档

- [百万字单机支持设计](docs/superpowers/specs/2026-07-16-million-char-support-design.md)
- [全链路优化规格](docs/superpowers/specs/2026-07-15-full-pipeline-optimization.md)
- [Phase 0～3 实施计划](docs/superpowers/plans/2026-07-15-phase0-3-optimization.md)

## 百万字小说指南（单机）

长篇（约 80 万～100 万+ 汉字）建议过夜跑；保持单进程 FastAPI，**不**依赖 Redis/Celery。

### 推荐环境变量

| 变量 | 建议 | 说明 |
|------|------|------|
| `AIVP_EXTRACT_WORKERS` | `4` | 抽取线程池并发 |
| `AIVP_EXTRACT_PROGRESS_EVERY` | `10` | 每 N 个 chunk 提交一次进度（防 SQLite 写放大） |
| `AIVP_CHUNK_SIZE` | `6000` | 比默认 4000 更大可减少 chunk 数与 LLM 调用 |
| `AIVP_CHUNK_OVERLAP` | `500` | 与 chunk_size 匹配即可 |
| `AIVP_VOLUME_MAX_CHARS` | `80000` | 分卷字数上限 |
| `AIVP_VOLUME_MAX_CHAPTERS` | `40` | 分卷章数上限 |
| `AIVP_ENRICH_EVENT_WINDOW` | `40` | 事件 enrich 滑窗，避免只取前 80 条 |
| `AIVP_TIMELINE_PAGE_SIZE` / `AIVP_API_PAGE_SIZE` | `50` | 时间线/分镜分页 |

### 过夜跑与续跑

1. 上传全书 TXT → 启动任务。关闭浏览器**不会**停后台 job。
2. 失败或手动终止后，可用 `resume_from_step`（如 `04_extract`）续跑；extract 已落盘的 chunk 会跳过。
3. 卷进度在流水线页显示为 `卷 done/total`；chunk 进度仍为 `chunks_done/total`。
4. Bible 时间线、分镜页支持「加载更多」，完整事件保存在 `07_timeline/events.json` 与分页文件。

### 假数据验收

```bash
cd backend && python -m pytest tests/test_million_char_support.py -v
# 或加长文端到端（Fake LLM）
python ../scripts/verify_million_char_fake.py
```
