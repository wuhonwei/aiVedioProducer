# AIVP 文本层 Story Bible MVP

将长篇小说文本加工为结构化 **Story Bible**（人物、世界观、情节弧、时间线等），供后续视频/改编生产使用。本仓库为文本层 MVP：后端 FastAPI 流水线 + 前端控制台（项目、流水线、Bible 编辑、导出）。

## 环境要求

- **Python 3.12+**
- **Node.js**（建议 18+，用于前端）
- **Ollama**（可选）：本地 LLM，默认 `http://127.0.0.1:11434`；未启动时部分抽取阶段会失败，单元测试不依赖真实 Ollama

## 分支说明

本功能在 **`feature/text-layer-story-bible`** 分支开发，可通过 git worktree 与主仓库并行检出：

```bash
git worktree add ../text-layer-story-bible feature/text-layer-story-bible
```

## 一键启动（推荐）

Windows 下任选其一：

- 双击仓库根目录 `start-dev.bat`
- 或在 PowerShell 中执行：

```powershell
.\scripts\start-dev.ps1
```

脚本会安装依赖（首次）、打开两个终端分别跑后端 `:8000` 与前端 `:5173`，并尝试打开浏览器。关闭对应终端窗口即可停止。

## 后端

```bash
cd backend
pip install -e ".[dev]"
```

可选：复制环境变量示例并按需修改：

```bash
cp .env.example .env
```

启动 API（默认 `http://127.0.0.1:8000`）：

```bash
uvicorn aivp.api.app:create_app --factory --reload --port 8000
```

## 前端

```bash
cd frontend
npm i
npm run dev
```

开发服务器默认 `http://127.0.0.1:5173`，`/api` 请求通过 Vite 代理到后端 8000 端口。

## 测试

**后端**（在 `backend` 目录）：

```bash
python -m pytest -v
```

**前端**（在 `frontend` 目录）：

```bash
npm test
```

## 目录概览

| 路径 | 说明 |
|------|------|
| `backend/src/aivp/` | 流水线阶段、API、Story Bible 合并与导出 |
| `frontend/src/` | React 控制台页面与 API 客户端 |
| `backend/data/` | 运行时项目数据（可由 `AIVP_DATA_ROOT` 指定） |
