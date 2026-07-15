# AI Video Producer（AIVP）

将长篇小说加工为结构化 **Story Bible**、生产级分镜与资产计划，面向后续国风二次元视频生产。当前主分支为 **`master`**。

## 能力矩阵

**已支持**

- 文本层结构化流水线（清洗 → 章节 → chunk → 抽取 → 归一 → enrich → timeline → arcs → Bible）
- Story Bible 自动生成 + overlay 人工编辑与导出
- 分镜初步生成（DeepSeek / 启发式回退）
- 角色视觉候选图 stub、LoRA 训练包生成
- 项目 / 流水线 / Bible / 分镜 / 角色视觉 / 导出 / 设置控制台

**尚未支持（Phase 4～6）**

- 真实 ComfyUI 图像生成 workflow
- LTX / 其他 I2V 视频生成
- TTS 音频
- FFmpeg 成片

## 环境要求

- **Python 3.12+**
- **Node.js 18+**
- **Ollama**（可选）：默认 `http://127.0.0.1:11434`，模型 `qwen2.5:14b`
- **DeepSeek API**（可选）：分镜生成；未配置时使用启发式回退

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

- [全链路优化规格](docs/superpowers/specs/2026-07-15-full-pipeline-optimization.md)
- [Phase 0～3 实施计划](docs/superpowers/plans/2026-07-15-phase0-3-optimization.md)
