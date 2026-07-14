# 文本层 Story Bible 管线 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 交付本地可运行的文本层：上传百万字级 TXT → 分阶段流水线（Ollama 抽取）→ 完整 Story Bible（1–16）→ 前端浏览/编辑/版本导出，全程 TDD。

**Architecture:** FastAPI + 同机单 Worker 按阶段读写 `data/projects/{id}/stages/*` 工件；SQLite 存项目/任务元数据；Story Bible 以 `story_bible.auto.json` 为自动结果、`overlay` 为人改覆盖、导出为冻结版本；`LlmClient` 抽象对接 Ollama，测试用 FakeLlm。

**Tech Stack:** Python 3.12、FastAPI、SQLAlchemy、Pydantic v2、httpx、pytest、React 18、Vite、TypeScript、Vitest、Testing Library、Ollama。

**规格：** `docs/superpowers/specs/2026-07-14-text-layer-story-bible-design.md`

**首期锁定默认值：**
- Chunk：目标 1200 字，重叠 150 字
- Ollama：`http://127.0.0.1:11434`，模型 `qwen2.5:14b`（可配置）
- Worker：API 进程内 `threading.Thread`（单并发 job）
- Normalize：别名规则优先，冲突时再问 FakeLlm/Ollama

---

## 文件结构（新建）

```
backend/
  pyproject.toml
  src/aivp/
    __init__.py
    config.py                 # Settings（路径、ollama、chunk）
    paths.py                  # 项目目录约定
    db.py                     # SQLite engine/session
    models.py                 # Project, Job, JobStep ORM
    schemas.py                # API / Bible Pydantic
    llm/
      base.py                 # LlmClient Protocol
      fake.py
      ollama_client.py
    pipeline/
      types.py                # StageName 枚举与进度结构
      clean.py
      chapters.py
      chunks.py
      extract.py
      normalize.py
      timeline.py
      arcs.py
      assemble.py
      runner.py               # 调度与续跑
    bible/
      overlay.py              # JSON Merge Patch + 合并视图
      export_md.py
    api/
      app.py
      deps.py
      routes_projects.py
      routes_jobs.py
      routes_bible.py
      routes_health.py
  tests/
    conftest.py
    fixtures/sample_chapter.txt
    fixtures/fake_extract_responses.json
    test_clean.py
    test_chapters.py
    test_chunks.py
    test_extract.py
    test_normalize.py
    test_timeline.py
    test_arcs.py
    test_assemble.py
    test_overlay.py
    test_export.py
    test_runner.py
    test_api_projects.py
    test_api_jobs.py
    test_api_bible.py
    test_golden_pipeline.py
frontend/
  package.json
  vite.config.ts
  tsconfig.json
  index.html
  src/
    main.tsx
    App.tsx
    api/client.ts
    pages/ProjectListPage.tsx
    pages/PipelinePage.tsx
    pages/BiblePage.tsx
    pages/ExportPage.tsx
    pages/SettingsPage.tsx
  src/__tests__/
    PipelinePage.test.tsx
    BiblePage.test.tsx
```

---

### Task 1: Backend 脚手架与 Settings

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/src/aivp/__init__.py`
- Create: `backend/src/aivp/config.py`
- Create: `backend/tests/test_config.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_config.py
from aivp.config import Settings

def test_default_settings():
    s = Settings(data_root="/tmp/aivp-data")
    assert s.ollama_base_url == "http://127.0.0.1:11434"
    assert s.ollama_model == "qwen2.5:14b"
    assert s.chunk_size == 1200
    assert s.chunk_overlap == 150
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pip install -e ".[dev]" 2>nul; pytest tests/test_config.py -v`  
（若包装尚未安装会报 `ModuleNotFoundError: aivp` —— 预期失败）

- [ ] **Step 3: 最小实现**

```toml
# backend/pyproject.toml
[project]
name = "aivp"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
  "fastapi>=0.115",
  "uvicorn[standard]>=0.32",
  "sqlalchemy>=2.0",
  "pydantic>=2.9",
  "pydantic-settings>=2.6",
  "httpx>=0.27",
  "python-multipart>=0.0.12",
  "jsonpatch>=1.33",
]

[project.optional-dependencies]
dev = ["pytest>=8.3", "pytest-asyncio>=0.24"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/aivp"]

[tool.pytest.ini_options]
pythonpath = ["src"]
testpaths = ["tests"]
```

```python
# backend/src/aivp/__init__.py
__version__ = "0.1.0"
```

```python
# backend/src/aivp/config.py
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AIVP_")
    data_root: Path = Path("data")
    db_url: str = "sqlite:///./data/aivp.db"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:14b"
    chunk_size: int = 1200
    chunk_overlap: int = 150
    extract_max_retries: int = 2
    skip_bad_chunks: bool = True
```

- [ ] **Step 4: 安装并跑通测试**

Run: `cd backend && pip install -e ".[dev]" && pytest tests/test_config.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/pyproject.toml backend/src/aivp/__init__.py backend/src/aivp/config.py backend/tests/test_config.py
git commit -m "chore: scaffold backend package and settings"
```

---

### Task 2: 项目路径约定 `paths.py`

**Files:**
- Create: `backend/src/aivp/paths.py`
- Create: `backend/tests/test_paths.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_paths.py
from pathlib import Path
from aivp.paths import ProjectPaths

def test_project_paths_layout(tmp_path: Path):
    p = ProjectPaths(tmp_path, "proj1")
    p.ensure()
    assert p.source_txt.exists() is False
    assert p.raw_dir.is_dir()
    assert p.stages_dir.is_dir()
    assert p.overlay_json.name == "story_bible.overlay.json"
    assert p.auto_bible_json.name == "story_bible.auto.json"
    assert "01_clean" in str(p.clean_txt)
    assert p.extract_chunk_json("ch01", "0001").parent.name == "ch01"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_paths.py -v`  
Expected: FAIL `ImportError` 或属性缺失

- [ ] **Step 3: 实现**

```python
# backend/src/aivp/paths.py
from pathlib import Path

class ProjectPaths:
    def __init__(self, data_root: Path, project_id: str):
        self.root = data_root / "projects" / project_id
        self.raw_dir = self.root / "raw"
        self.stages_dir = self.root / "stages"
        self.overlays_dir = self.root / "overlays"
        self.exports_dir = self.root / "exports"
        self.source_txt = self.raw_dir / "source.txt"
        self.clean_txt = self.stages_dir / "01_clean" / "cleaned.txt"
        self.chapters_json = self.stages_dir / "02_chapters" / "chapters.json"
        self.chunks_jsonl = self.stages_dir / "03_chunks" / "chunks.jsonl"
        self.extract_dir = self.stages_dir / "04_extract"
        self.entities_json = self.stages_dir / "05_normalize" / "entities.json"
        self.events_json = self.stages_dir / "06_timeline" / "events.json"
        self.arcs_json = self.stages_dir / "07_arcs" / "arcs.json"
        self.auto_bible_json = self.stages_dir / "08_bible" / "story_bible.auto.json"
        self.overlay_json = self.overlays_dir / "story_bible.overlay.json"

    def ensure(self) -> None:
        for d in (
            self.raw_dir,
            self.stages_dir / "01_clean",
            self.stages_dir / "02_chapters",
            self.stages_dir / "03_chunks",
            self.extract_dir,
            self.stages_dir / "05_normalize",
            self.stages_dir / "06_timeline",
            self.stages_dir / "07_arcs",
            self.stages_dir / "08_bible",
            self.overlays_dir,
            self.exports_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def extract_chunk_json(self, chapter_id: str, chunk_id: str) -> Path:
        return self.extract_dir / chapter_id / f"{chunk_id}.json"
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_paths.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/paths.py backend/tests/test_paths.py
git commit -m "feat: add project directory path helpers"
```

---

### Task 3: Clean 阶段

**Files:**
- Create: `backend/src/aivp/pipeline/clean.py`
- Create: `backend/tests/test_clean.py`
- Create: `backend/tests/fixtures/messy.txt`

- [ ] **Step 1: 准备夹具并写失败测试**

```text
# backend/tests/fixtures/messy.txt  (用 UTF-8 BOM + \r\n + 多余空行)
（写入时用 Python 生成，见 Step 3 测试也可在测试内构造）
```

```python
# backend/tests/test_clean.py
from pathlib import Path
from aivp.pipeline.clean import clean_text, run_clean

def test_clean_text_normalizes_newlines_and_bom():
    raw = "\ufeff甲\r\n\r\n\r\n乙\r\n"
    assert clean_text(raw) == "甲\n\n乙\n"

def test_run_clean_writes_file(tmp_path: Path):
    src = tmp_path / "source.txt"
    out = tmp_path / "cleaned.txt"
    src.write_text("\ufeff章一\r\n\r\n内容", encoding="utf-8")
    run_clean(src, out)
    assert out.read_text(encoding="utf-8") == "章一\n\n内容\n"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_clean.py -v`  
Expected: FAIL import

- [ ] **Step 3: 实现**

```python
# backend/src/aivp/pipeline/__init__.py
```

```python
# backend/src/aivp/pipeline/clean.py
from pathlib import Path

def clean_text(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text

def run_clean(source: Path, dest: Path) -> Path:
    raw = source.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("unable_to_decode_source")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(clean_text(text), encoding="utf-8")
    return dest
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_clean.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/pipeline/clean.py backend/src/aivp/pipeline/__init__.py backend/tests/test_clean.py
git commit -m "feat: add text clean stage"
```

---

### Task 4: ChapterSplit 阶段

**Files:**
- Create: `backend/src/aivp/pipeline/chapters.py`
- Create: `backend/tests/test_chapters.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_chapters.py
from aivp.pipeline.chapters import split_chapters

SAMPLE = """第一章 山雨欲来

正文甲。

第二章 夜宴

正文乙。
"""

def test_split_chapters_by_cn_heading():
    chapters = split_chapters(SAMPLE)
    assert len(chapters) == 2
    assert chapters[0]["id"] == "ch001"
    assert chapters[0]["title"] == "第一章 山雨欲来"
    assert "正文甲" in chapters[0]["text"]
    assert chapters[1]["title"] == "第二章 夜宴"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_chapters.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# backend/src/aivp/pipeline/chapters.py
import json
import re
from pathlib import Path

HEADING_RE = re.compile(
    r"^(第[零一二三四五六七八九十百千0-9]+章\s*.+)$",
    re.MULTILINE,
)

def split_chapters(text: str) -> list[dict]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        body = text.strip()
        if not body:
            raise ValueError("chapter_split_empty")
        return [{"id": "ch001", "index": 1, "title": "全文", "text": body}]
    chapters: list[dict] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        title = m.group(1).strip()
        body = block[len(title):].strip()
        chapters.append({
            "id": f"ch{i+1:03d}",
            "index": i + 1,
            "title": title,
            "text": body,
        })
    return chapters

def run_chapter_split(clean_txt: Path, out_json: Path) -> list[dict]:
    chapters = split_chapters(clean_txt.read_text(encoding="utf-8"))
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")
    return chapters
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_chapters.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/pipeline/chapters.py backend/tests/test_chapters.py
git commit -m "feat: add Chinese chapter split stage"
```

---

### Task 5: Chunk 阶段

**Files:**
- Create: `backend/src/aivp/pipeline/chunks.py`
- Create: `backend/tests/test_chunks.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_chunks.py
from aivp.pipeline.chunks import chunk_chapters

def test_chunk_respects_size_and_overlap():
    chapters = [{"id": "ch001", "index": 1, "title": "T", "text": "字" * 2500}]
    chunks = chunk_chapters(chapters, size=1200, overlap=150)
    assert len(chunks) >= 2
    assert chunks[0]["chapter_id"] == "ch001"
    assert chunks[0]["id"] == "0001"
    assert len(chunks[0]["text"]) <= 1200
    # overlap: second chunk starts within first chunk's tail
    assert chunks[1]["text"][:50] in chunks[0]["text"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_chunks.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# backend/src/aivp/pipeline/chunks.py
import json
from pathlib import Path

def chunk_chapters(chapters: list[dict], size: int = 1200, overlap: int = 150) -> list[dict]:
    if overlap >= size:
        raise ValueError("overlap_must_be_lt_size")
    out: list[dict] = []
    for ch in chapters:
        text = ch["text"]
        if not text:
            continue
        start = 0
        idx = 1
        while start < len(text):
            end = min(start + size, len(text))
            piece = text[start:end]
            out.append({
                "id": f"{idx:04d}",
                "chapter_id": ch["id"],
                "chapter_title": ch["title"],
                "index": idx,
                "text": piece,
            })
            if end >= len(text):
                break
            start = end - overlap
            idx += 1
    return out

def run_chunk(chapters_json: Path, out_jsonl: Path, size: int, overlap: int) -> list[dict]:
    chapters = json.loads(chapters_json.read_text(encoding="utf-8"))
    chunks = chunk_chapters(chapters, size=size, overlap=overlap)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return chunks
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_chunks.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/pipeline/chunks.py backend/tests/test_chunks.py
git commit -m "feat: add chapter chunking stage"
```

---

### Task 6: LlmClient + FakeLlm + Ollama 客户端

**Files:**
- Create: `backend/src/aivp/llm/base.py`
- Create: `backend/src/aivp/llm/fake.py`
- Create: `backend/src/aivp/llm/ollama_client.py`
- Create: `backend/tests/test_llm_fake.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_llm_fake.py
from aivp.llm.fake import FakeLlm

def test_fake_llm_returns_scripted_json():
    llm = FakeLlm(script={"hello": {"ok": True}})
    assert llm.complete_json("sys", "hello") == {"ok": True}

def test_fake_llm_missing_key_raises():
    llm = FakeLlm(script={})
    try:
        llm.complete_json("sys", "missing")
        assert False, "expected KeyError"
    except KeyError:
        pass
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_llm_fake.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# backend/src/aivp/llm/__init__.py
```

```python
# backend/src/aivp/llm/base.py
from typing import Any, Protocol

class LlmClient(Protocol):
    def complete_json(self, system: str, user: str) -> dict[str, Any]: ...
```

```python
# backend/src/aivp/llm/fake.py
from typing import Any

class FakeLlm:
    def __init__(self, script: dict[str, dict[str, Any]] | None = None, default: dict[str, Any] | None = None):
        self.script = script or {}
        self.default = default
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        self.calls.append((system, user))
        if user in self.script:
            return self.script[user]
        if self.default is not None:
            return self.default
        raise KeyError(f"no_fake_response_for:{user[:80]}")
```

```python
# backend/src/aivp/llm/ollama_client.py
import json
from typing import Any
import httpx

class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout

    def complete_json(self, system: str, user: str) -> dict[str, Any]:
        payload = {
            "model": self.model,
            "stream": False,
            "format": "json",
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
        with httpx.Client(timeout=self.timeout) as client:
            r = client.post(f"{self.base_url}/api/chat", json=payload)
            r.raise_for_status()
            content = r.json()["message"]["content"]
        return json.loads(content)

    def healthy(self) -> bool:
        try:
            with httpx.Client(timeout=5.0) as client:
                r = client.get(f"{self.base_url}/api/tags")
                return r.status_code == 200
        except httpx.HTTPError:
            return False
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_llm_fake.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/llm backend/tests/test_llm_fake.py
git commit -m "feat: add LlmClient protocol with Fake and Ollama"
```

---

### Task 7: Extract 阶段（schema + FakeLlm）

**Files:**
- Create: `backend/src/aivp/pipeline/extract.py`
- Create: `backend/src/aivp/schemas.py`（ChunkExtract 模型）
- Create: `backend/tests/test_extract.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_extract.py
from pathlib import Path
import json
from aivp.llm.fake import FakeLlm
from aivp.pipeline.extract import extract_chunk, run_extract
from aivp.paths import ProjectPaths

def test_extract_chunk_validates_schema():
    llm = FakeLlm(default={
        "characters": [{"name": "李青云", "aliases": ["青云"]}],
        "locations": [{"name": "青云山"}],
        "factions": [],
        "props": [],
        "events": [{"summary": "比武"}],
        "foreshadowing": [],
        "visual_cues": ["水墨远山"],
        "voice_cues": [],
        "adaptation_notes": [],
    })
    chunk = {"id": "0001", "chapter_id": "ch001", "chapter_title": "第一章", "text": "李青云在青云山比武。"}
    result = extract_chunk(chunk, llm)
    assert result["characters"][0]["name"] == "李青云"

def test_run_extract_writes_files(tmp_path: Path):
    paths = ProjectPaths(tmp_path, "p1")
    paths.ensure()
    chunk = {"id": "0001", "chapter_id": "ch001", "chapter_title": "T", "text": "甲"}
    paths.chunks_jsonl.write_text(json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8")
    llm = FakeLlm(default={
        "characters": [], "locations": [], "factions": [], "props": [],
        "events": [], "foreshadowing": [], "visual_cues": [], "voice_cues": [],
        "adaptation_notes": [],
    })
    run_extract(paths, llm, max_retries=1, skip_bad=True)
    out = paths.extract_chunk_json("ch001", "0001")
    assert out.exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_extract.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# backend/src/aivp/schemas.py
from typing import Any
from pydantic import BaseModel, Field

class NamedEntity(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)

class ChunkExtract(BaseModel):
    characters: list[NamedEntity] = Field(default_factory=list)
    locations: list[NamedEntity] = Field(default_factory=list)
    factions: list[NamedEntity] = Field(default_factory=list)
    props: list[NamedEntity] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    foreshadowing: list[dict[str, Any]] = Field(default_factory=list)
    visual_cues: list[str] = Field(default_factory=list)
    voice_cues: list[str] = Field(default_factory=list)
    adaptation_notes: list[str] = Field(default_factory=list)

REQUIRED_BIBLE_KEYS = [
    "project_meta", "logline", "worldbuilding", "plot_structure", "characters",
    "character_relations", "locations", "factions", "props", "timeline",
    "foreshadowing", "adaptation_notes", "visual_style", "character_visuals",
    "voice_bible", "production_constraints",
]
```

```python
# backend/src/aivp/pipeline/extract.py
import json
from pathlib import Path
from aivp.llm.base import LlmClient
from aivp.paths import ProjectPaths
from aivp.schemas import ChunkExtract

SYSTEM = (
    "你是国风长篇结构化抽取器。只输出 JSON，键必须匹配给定 schema。"
    "缺信息用空数组。不要输出 markdown。"
)

def extract_chunk(chunk: dict, llm: LlmClient, max_retries: int = 2) -> dict:
    user = (
        f"章节:{chunk.get('chapter_title','')}\n"
        f"正文:\n{chunk['text']}\n"
        "请抽取 characters/locations/factions/props/events/"
        "foreshadowing/visual_cues/voice_cues/adaptation_notes"
    )
    last_err: Exception | None = None
    for _ in range(max_retries + 1):
        try:
            raw = llm.complete_json(SYSTEM, user if _ == 0 else user + "\n请严格修复为合法 JSON schema。")
            return ChunkExtract.model_validate(raw).model_dump()
        except Exception as e:  # noqa: BLE001 — 校验/JSON 统一重试
            last_err = e
    raise ValueError(f"extract_failed:{chunk['id']}:{last_err}")

def run_extract(paths: ProjectPaths, llm: LlmClient, max_retries: int, skip_bad: bool) -> dict:
    chunks = [
        json.loads(line)
        for line in paths.chunks_jsonl.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    errors: list[str] = []
    done = 0
    for chunk in chunks:
        dest = paths.extract_chunk_json(chunk["chapter_id"], chunk["id"])
        if dest.exists():
            done += 1
            continue
        try:
            data = extract_chunk(chunk, llm, max_retries=max_retries)
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            done += 1
        except Exception as e:  # noqa: BLE001
            errors.append(str(e))
            if not skip_bad:
                raise
    return {"total": len(chunks), "done": done, "errors": errors}
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_extract.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/schemas.py backend/src/aivp/pipeline/extract.py backend/tests/test_extract.py
git commit -m "feat: add chunk extract stage with schema validation"
```

---

### Task 8: Normalize + Timeline + Arcs

**Files:**
- Create: `backend/src/aivp/pipeline/normalize.py`
- Create: `backend/src/aivp/pipeline/timeline.py`
- Create: `backend/src/aivp/pipeline/arcs.py`
- Create: `backend/tests/test_normalize.py`
- Create: `backend/tests/test_timeline.py`
- Create: `backend/tests/test_arcs.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_normalize.py
from aivp.pipeline.normalize import normalize_entities

def test_normalize_merges_aliases():
    extracts = [
        {"characters": [{"name": "李青云", "aliases": ["青云"]}], "locations": [], "factions": [], "props": []},
        {"characters": [{"name": "青云", "aliases": []}], "locations": [], "factions": [], "props": []},
    ]
    entities = normalize_entities(extracts)
    names = [c["name"] for c in entities["characters"]]
    assert names.count("李青云") == 1
    assert "青云" in entities["characters"][0]["aliases"]
```

```python
# backend/tests/test_timeline.py
from aivp.pipeline.timeline import build_timeline

def test_timeline_orders_by_chapter_then_index():
    chunks_meta = [
        {"id": "0001", "chapter_id": "ch001", "index": 1},
        {"id": "0001", "chapter_id": "ch002", "index": 1},
    ]
    extracts = {
        ("ch001", "0001"): {"events": [{"summary": "相遇"}]},
        ("ch002", "0001"): {"events": [{"summary": "决裂"}]},
    }
    events = build_timeline(chunks_meta, extracts)
    assert [e["summary"] for e in events] == ["相遇", "决裂"]
    assert events[0]["id"] == "evt0001"
```

```python
# backend/tests/test_arcs.py
from aivp.pipeline.arcs import build_arcs

def test_build_arcs_groups_by_chapter():
    chapters = [{"id": "ch001", "title": "第一章 开端"}, {"id": "ch002", "title": "第二章 高潮"}]
    events = [
        {"id": "evt0001", "chapter_id": "ch001", "summary": "相遇"},
        {"id": "evt0002", "chapter_id": "ch002", "summary": "决裂"},
    ]
    arcs = build_arcs(chapters, events)
    assert len(arcs) == 2
    assert arcs[0]["chapter_id"] == "ch001"
    assert "相遇" in arcs[0]["summary"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_normalize.py tests/test_timeline.py tests/test_arcs.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# backend/src/aivp/pipeline/normalize.py
import json
from pathlib import Path

def _merge_group(items: list[dict]) -> list[dict]:
    by_key: dict[str, dict] = {}
    alias_to_canonical: dict[str, str] = {}
    for item in items:
        name = item["name"].strip()
        aliases = [a.strip() for a in item.get("aliases", []) if a.strip()]
        canon = alias_to_canonical.get(name, name)
        for a in aliases:
            if a in alias_to_canonical:
                canon = alias_to_canonical[a]
        if canon not in by_key:
            by_key[canon] = {"id": f"ent_{len(by_key)+1:04d}", "name": canon, "aliases": []}
        entry = by_key[canon]
        for a in [name, *aliases]:
            if a != entry["name"] and a not in entry["aliases"]:
                entry["aliases"].append(a)
            alias_to_canonical[a] = entry["name"]
    return list(by_key.values())

def normalize_entities(extracts: list[dict]) -> dict:
    buckets = {"characters": [], "locations": [], "factions": [], "props": []}
    for ex in extracts:
        for k in buckets:
            buckets[k].extend(ex.get(k, []))
    return {k: _merge_group(v) for k, v in buckets.items()}

def run_normalize(extract_dir: Path, out_json: Path) -> dict:
    extracts: list[dict] = []
    for path in sorted(extract_dir.glob("*/*.json")):
        extracts.append(json.loads(path.read_text(encoding="utf-8")))
    entities = normalize_entities(extracts)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(entities, ensure_ascii=False, indent=2), encoding="utf-8")
    return entities
```

```python
# backend/src/aivp/pipeline/timeline.py
import json
from pathlib import Path

def build_timeline(chunks_meta: list[dict], extracts: dict[tuple[str, str], dict]) -> list[dict]:
    ordered = sorted(chunks_meta, key=lambda c: (c["chapter_id"], c["index"]))
    events: list[dict] = []
    n = 1
    for c in ordered:
        key = (c["chapter_id"], c["id"])
        for ev in extracts.get(key, {}).get("events", []):
            events.append({
                "id": f"evt{n:04d}",
                "chapter_id": c["chapter_id"],
                "chunk_id": c["id"],
                "summary": ev.get("summary", ""),
                "raw": ev,
            })
            n += 1
    return events

def run_timeline(chunks_jsonl: Path, extract_dir: Path, out_json: Path) -> list[dict]:
    chunks_meta = [json.loads(l) for l in chunks_jsonl.read_text(encoding="utf-8").splitlines() if l.strip()]
    extracts: dict[tuple[str, str], dict] = {}
    for path in extract_dir.glob("*/*.json"):
        extracts[(path.parent.name, path.stem)] = json.loads(path.read_text(encoding="utf-8"))
    events = build_timeline(chunks_meta, extracts)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    return events
```

```python
# backend/src/aivp/pipeline/arcs.py
import json
from pathlib import Path

def build_arcs(chapters: list[dict], events: list[dict]) -> list[dict]:
    by_ch: dict[str, list[str]] = {}
    for e in events:
        by_ch.setdefault(e["chapter_id"], []).append(e["summary"])
    arcs = []
    for ch in chapters:
        summaries = by_ch.get(ch["id"], [])
        arcs.append({
            "id": f"arc_{ch['id']}",
            "chapter_id": ch["id"],
            "title": ch["title"],
            "summary": "；".join(summaries) if summaries else "",
        })
    return arcs

def run_arcs(chapters_json: Path, events_json: Path, out_json: Path) -> list[dict]:
    chapters = json.loads(chapters_json.read_text(encoding="utf-8"))
    events = json.loads(events_json.read_text(encoding="utf-8"))
    arcs = build_arcs(chapters, events)
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(arcs, ensure_ascii=False, indent=2), encoding="utf-8")
    return arcs
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_normalize.py tests/test_timeline.py tests/test_arcs.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/pipeline/normalize.py backend/src/aivp/pipeline/timeline.py backend/src/aivp/pipeline/arcs.py backend/tests/test_normalize.py backend/tests/test_timeline.py backend/tests/test_arcs.py
git commit -m "feat: add normalize, timeline, and arcs stages"
```

---

### Task 9: Assemble Story Bible（1–16 键齐全）

**Files:**
- Create: `backend/src/aivp/pipeline/assemble.py`
- Create: `backend/tests/test_assemble.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_assemble.py
from aivp.pipeline.assemble import assemble_bible
from aivp.schemas import REQUIRED_BIBLE_KEYS

def test_assemble_includes_all_16_keys():
    bible = assemble_bible(
        project_name="测书",
        chapters=[{"id": "ch001", "title": "第一章", "text": "甲"}],
        entities={"characters": [{"id": "ent_0001", "name": "李青云", "aliases": []}], "locations": [], "factions": [], "props": []},
        events=[{"id": "evt0001", "chapter_id": "ch001", "summary": "相遇"}],
        arcs=[{"id": "arc_ch001", "chapter_id": "ch001", "title": "第一章", "summary": "相遇"}],
        extracts=[{"foreshadowing": [{"note": "剑冢"}], "visual_cues": ["水墨"], "voice_cues": ["低沉男声"], "adaptation_notes": ["开场冷开"]}],
        warnings=["skip:ch001/0002"],
    )
    for k in REQUIRED_BIBLE_KEYS:
        assert k in bible
    assert bible["characters"][0]["name"] == "李青云"
    assert bible["warnings"] == ["skip:ch001/0002"]
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_assemble.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# backend/src/aivp/pipeline/assemble.py
import json
from datetime import datetime, timezone
from pathlib import Path
from aivp.schemas import REQUIRED_BIBLE_KEYS

def assemble_bible(
    *,
    project_name: str,
    chapters: list[dict],
    entities: dict,
    events: list[dict],
    arcs: list[dict],
    extracts: list[dict],
    warnings: list[str] | None = None,
) -> dict:
    foreshadowing: list = []
    visual_cues: list[str] = []
    voice_cues: list[str] = []
    adaptation_notes: list[str] = []
    for ex in extracts:
        foreshadowing.extend(ex.get("foreshadowing", []))
        visual_cues.extend(ex.get("visual_cues", []))
        voice_cues.extend(ex.get("voice_cues", []))
        adaptation_notes.extend(ex.get("adaptation_notes", []))

    chars = entities.get("characters", [])
    bible = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source_stats": {"chapter_count": len(chapters), "event_count": len(events)},
        "warnings": warnings or [],
        "project_meta": {"title": project_name, "language": "zh-CN", "genre": "国风"},
        "logline": arcs[0]["summary"] if arcs else "",
        "worldbuilding": {"summary": "", "rules": []},
        "plot_structure": {"arcs": arcs, "chapters": [{"id": c["id"], "title": c["title"]} for c in chapters]},
        "characters": chars,
        "character_relations": [],
        "locations": entities.get("locations", []),
        "factions": entities.get("factions", []),
        "props": entities.get("props", []),
        "timeline": events,
        "foreshadowing": foreshadowing,
        "adaptation_notes": adaptation_notes,
        "visual_style": {"summary": "；".join(dict.fromkeys(visual_cues)), "keywords": list(dict.fromkeys(visual_cues))},
        "character_visuals": [{"character_id": c.get("id"), "name": c.get("name"), "notes": ""} for c in chars],
        "voice_bible": {"cues": list(dict.fromkeys(voice_cues)), "cast": []},
        "production_constraints": {"max_chars_on_screen": 3, "notes": []},
    }
    for k in REQUIRED_BIBLE_KEYS:
        bible.setdefault(k, {} if k not in ("characters", "character_relations", "locations", "factions", "props", "timeline", "foreshadowing", "adaptation_notes") else [])
    return bible

def run_assemble(paths, project_name: str, warnings: list[str] | None = None) -> dict:
    chapters = json.loads(paths.chapters_json.read_text(encoding="utf-8"))
    entities = json.loads(paths.entities_json.read_text(encoding="utf-8"))
    events = json.loads(paths.events_json.read_text(encoding="utf-8"))
    arcs = json.loads(paths.arcs_json.read_text(encoding="utf-8"))
    extracts = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(paths.extract_dir.glob("*/*.json"))]
    bible = assemble_bible(
        project_name=project_name,
        chapters=chapters,
        entities=entities,
        events=events,
        arcs=arcs,
        extracts=extracts,
        warnings=warnings,
    )
    paths.auto_bible_json.parent.mkdir(parents=True, exist_ok=True)
    paths.auto_bible_json.write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8")
    return bible
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_assemble.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/pipeline/assemble.py backend/tests/test_assemble.py
git commit -m "feat: assemble full 16-section story bible"
```

---

### Task 10: Overlay 合并与导出

**Files:**
- Create: `backend/src/aivp/bible/overlay.py`
- Create: `backend/src/aivp/bible/export_md.py`
- Create: `backend/tests/test_overlay.py`
- Create: `backend/tests/test_export.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/test_overlay.py
from aivp.bible.overlay import merge_bible, apply_merge_patch, unset_path

def test_merge_overlay_wins():
    auto = {"logline": "自动", "characters": []}
    overlay = {"logline": "人工"}
    assert merge_bible(auto, overlay)["logline"] == "人工"

def test_apply_merge_patch_and_unset():
    overlay: dict = {}
    overlay = apply_merge_patch(overlay, {"logline": "改"})
    assert overlay["logline"] == "改"
    overlay = unset_path(overlay, "/logline")
    assert "logline" not in overlay
```

```python
# backend/tests/test_export.py
from pathlib import Path
from aivp.bible.export_md import export_version

def test_export_writes_json_and_md(tmp_path: Path):
    bible = {"project_meta": {"title": "测"}, "logline": "一句话", "warnings": []}
    # fill required keys minimally
    for k in [
        "worldbuilding","plot_structure","characters","character_relations","locations",
        "factions","props","timeline","foreshadowing","adaptation_notes","visual_style",
        "character_visuals","voice_bible","production_constraints",
    ]:
        bible.setdefault(k, {} if k not in ("characters","timeline") else [])
    paths = export_version(tmp_path, bible, version=1)
    assert paths["json"].name == "story_bible.v001.json"
    assert "一句话" in paths["md"].read_text(encoding="utf-8")
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_overlay.py tests/test_export.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现**

```python
# backend/src/aivp/bible/__init__.py
```

```python
# backend/src/aivp/bible/overlay.py
import copy
from typing import Any
import jsonpatch

def merge_bible(auto: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(auto)
    def deep_merge(a: dict, b: dict) -> dict:
        for k, v in b.items():
            if isinstance(v, dict) and isinstance(a.get(k), dict):
                deep_merge(a[k], v)
            else:
                a[k] = copy.deepcopy(v)
        return a
    return deep_merge(result, overlay or {})

def apply_merge_patch(overlay: dict[str, Any], patch: dict[str, Any]) -> dict[str, Any]:
    # RFC 7396 via jsonpatch's JsonMergePatch if available; fallback deep merge
    base = copy.deepcopy(overlay)
    return merge_bible(base, patch)

def unset_path(overlay: dict[str, Any], pointer: str) -> dict[str, Any]:
    # pointer like /logline or /characters
    parts = [p for p in pointer.split("/") if p]
    if not parts:
        return overlay
    cur: Any = overlay
    for p in parts[:-1]:
        if not isinstance(cur, dict) or p not in cur:
            return overlay
        cur = cur[p]
    if isinstance(cur, dict):
        cur.pop(parts[-1], None)
    return overlay
```

```python
# backend/src/aivp/bible/export_md.py
import json
from pathlib import Path

SECTION_TITLES = [
    ("project_meta", "1. 项目元信息"),
    ("logline", "2. 故事一句话概括"),
    ("worldbuilding", "3. 世界观设定"),
    ("plot_structure", "4. 主线剧情 / 篇章结构"),
    ("characters", "5. 主要角色 Bible"),
    ("character_relations", "6. 角色关系"),
    ("locations", "7. 地点 / 场景 Bible"),
    ("factions", "8. 组织 / 阵营 / 势力"),
    ("props", "9. 重要道具 / 法宝 / 物件"),
    ("timeline", "10. 事件时间线"),
    ("foreshadowing", "11. 伏笔 / 悬念 / 回收"),
    ("adaptation_notes", "12. 影视化改编信息"),
    ("visual_style", "13. 视觉风格 Bible"),
    ("character_visuals", "14. 角色视觉设定"),
    ("voice_bible", "15. 声音设定 Voice Bible"),
    ("production_constraints", "16. 分镜/资产生产约束"),
]

def bible_to_markdown(bible: dict) -> str:
    lines = ["# Story Bible", ""]
    for key, title in SECTION_TITLES:
        lines.append(f"## {title}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(bible.get(key), ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)

def export_version(exports_dir: Path, bible: dict, version: int) -> dict[str, Path]:
    exports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"story_bible.v{version:03d}"
    json_path = exports_dir / f"{stem}.json"
    md_path = exports_dir / f"{stem}.md"
    json_path.write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(bible_to_markdown(bible), encoding="utf-8")
    return {"json": json_path, "md": md_path}
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_overlay.py tests/test_export.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/bible backend/tests/test_overlay.py backend/tests/test_export.py
git commit -m "feat: add bible overlay merge and versioned export"
```

---

### Task 11: SQLite 模型与 Pipeline Runner（含续跑）

**Files:**
- Create: `backend/src/aivp/db.py`
- Create: `backend/src/aivp/models.py`
- Create: `backend/src/aivp/pipeline/types.py`
- Create: `backend/src/aivp/pipeline/runner.py`
- Create: `backend/tests/conftest.py`
- Create: `backend/tests/test_runner.py`

- [ ] **Step 1: 写失败测试**

```python
# backend/tests/conftest.py
import pytest
from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from aivp.db import Base
from aivp.config import Settings

@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'t.db'}")

@pytest.fixture
def db_session(settings: Settings):
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()
```

```python
# backend/tests/test_runner.py
from pathlib import Path
from aivp.models import Project, Job
from aivp.paths import ProjectPaths
from aivp.llm.fake import FakeLlm
from aivp.pipeline.runner import run_job
from aivp.config import Settings

SAMPLE = "第一章 开端\n\n李青云走进青云山。\n\n第二章 风云\n\n青云拔剑。\n"

def test_runner_full_pipeline_with_fake_llm(db_session, settings: Settings):
    proj = Project(id="p1", name="测书")
    db_session.add(proj)
    db_session.commit()
    paths = ProjectPaths(settings.data_root, "p1")
    paths.ensure()
    paths.source_txt.write_text(SAMPLE, encoding="utf-8")
    job = Job(id="j1", project_id="p1", status="queued")
    db_session.add(job)
    db_session.commit()
    llm = FakeLlm(default={
        "characters": [{"name": "李青云", "aliases": ["青云"]}],
        "locations": [{"name": "青云山", "aliases": []}],
        "factions": [], "props": [],
        "events": [{"summary": "入山"}],
        "foreshadowing": [], "visual_cues": ["远山"], "voice_cues": [],
        "adaptation_notes": [],
    })
    run_job(db_session, settings, job_id="j1", llm=llm)
    db_session.refresh(job)
    assert job.status == "succeeded"
    assert paths.auto_bible_json.exists()
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_runner.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现 db/models/types/runner**

```python
# backend/src/aivp/db.py
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass
```

```python
# backend/src/aivp/models.py
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from aivp.db import Base

def _utcnow():
    return datetime.now(timezone.utc)

class Project(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    export_version: Mapped[int] = mapped_column(Integer, default=0)

class Job(Base):
    __tablename__ = "jobs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"))
    status: Mapped[str] = mapped_column(String(32), default="queued")
    current_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    chunks_total: Mapped[int] = mapped_column(Integer, default=0)
    chunks_done: Mapped[int] = mapped_column(Integer, default=0)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    resume_from_step: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)

class JobStep(Base):
    __tablename__ = "job_steps"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[str] = mapped_column(ForeignKey("jobs.id"))
    step: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32))
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
```

```python
# backend/src/aivp/pipeline/types.py
STAGE_ORDER = [
    "01_clean",
    "02_chapters",
    "03_chunks",
    "04_extract",
    "05_normalize",
    "06_timeline",
    "07_arcs",
    "08_bible",
]
```

```python
# backend/src/aivp/pipeline/runner.py
import json
from sqlalchemy.orm import Session
from aivp.config import Settings
from aivp.models import Job, JobStep, Project
from aivp.paths import ProjectPaths
from aivp.pipeline.types import STAGE_ORDER
from aivp.pipeline.clean import run_clean
from aivp.pipeline.chapters import run_chapter_split
from aivp.pipeline.chunks import run_chunk
from aivp.pipeline.extract import run_extract
from aivp.pipeline.normalize import run_normalize
from aivp.pipeline.timeline import run_timeline
from aivp.pipeline.arcs import run_arcs
from aivp.pipeline.assemble import run_assemble

def run_job(session: Session, settings: Settings, job_id: str, llm) -> None:
    job = session.get(Job, job_id)
    if not job:
        raise KeyError(job_id)
    project = session.get(Project, job.project_id)
    paths = ProjectPaths(settings.data_root, job.project_id)
    paths.ensure()
    start_idx = 0
    if job.resume_from_step and job.resume_from_step in STAGE_ORDER:
        start_idx = STAGE_ORDER.index(job.resume_from_step)
    job.status = "running"
    session.commit()
    warnings: list[str] = []
    try:
        for step in STAGE_ORDER[start_idx:]:
            job.current_step = step
            session.add(JobStep(job_id=job.id, step=step, status="running"))
            session.commit()
            if step == "01_clean":
                run_clean(paths.source_txt, paths.clean_txt)
            elif step == "02_chapters":
                run_chapter_split(paths.clean_txt, paths.chapters_json)
            elif step == "03_chunks":
                chunks = run_chunk(paths.chapters_json, paths.chunks_jsonl, settings.chunk_size, settings.chunk_overlap)
                job.chunks_total = len(chunks)
            elif step == "04_extract":
                result = run_extract(paths, llm, settings.extract_max_retries, settings.skip_bad_chunks)
                job.chunks_done = result["done"]
                warnings.extend(result.get("errors", []))
            elif step == "05_normalize":
                run_normalize(paths.extract_dir, paths.entities_json)
            elif step == "06_timeline":
                run_timeline(paths.chunks_jsonl, paths.extract_dir, paths.events_json)
            elif step == "07_arcs":
                run_arcs(paths.chapters_json, paths.events_json, paths.arcs_json)
            elif step == "08_bible":
                run_assemble(paths, project.name, warnings=warnings)
            session.add(JobStep(job_id=job.id, step=step, status="succeeded"))
            session.commit()
        job.status = "succeeded"
        job.error_message = None
        session.commit()
    except Exception as e:  # noqa: BLE001
        job.status = "step_failed"
        job.error_message = str(e)
        session.add(JobStep(job_id=job.id, step=job.current_step or "unknown", status="failed", detail=str(e)))
        session.commit()
        raise
```

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_runner.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/db.py backend/src/aivp/models.py backend/src/aivp/pipeline/types.py backend/src/aivp/pipeline/runner.py backend/tests/conftest.py backend/tests/test_runner.py
git commit -m "feat: add sqlite models and resumable pipeline runner"
```

---

### Task 12: FastAPI 路由（项目/任务/Bible/健康检查）

**Files:**
- Create: `backend/src/aivp/api/app.py`
- Create: `backend/src/aivp/api/deps.py`
- Create: `backend/src/aivp/api/routes_projects.py`
- Create: `backend/src/aivp/api/routes_jobs.py`
- Create: `backend/src/aivp/api/routes_bible.py`
- Create: `backend/src/aivp/api/routes_health.py`
- Create: `backend/tests/test_api_projects.py`
- Create: `backend/tests/test_api_jobs.py`
- Create: `backend/tests/test_api_bible.py`

- [ ] **Step 1: 写 API 失败测试（项目创建 + 上传）**

```python
# backend/tests/test_api_projects.py
from fastapi.testclient import TestClient
from aivp.api.app import create_app
from aivp.config import Settings

def test_create_and_list_projects(tmp_path):
    app = create_app(Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'a.db'}"))
    client = TestClient(app)
    r = client.post("/api/projects", json={"name": "仙侠测"})
    assert r.status_code == 201
    pid = r.json()["id"]
    files = {"file": ("book.txt", b"第一章\n\n你好", "text/plain")}
    up = client.post(f"/api/projects/{pid}/source", files=files)
    assert up.status_code == 200
    assert client.get("/api/projects").json()[0]["name"] == "仙侠测"
```

```python
# backend/tests/test_api_bible.py
import json
from fastapi.testclient import TestClient
from aivp.api.app import create_app
from aivp.config import Settings
from aivp.paths import ProjectPaths

def test_bible_patch_and_get_merged(tmp_path):
    settings = Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path/'a.db'}")
    app = create_app(settings)
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "X"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    auto = {"logline": "自动", "characters": [], "project_meta": {"title": "X"}}
    for k in ["worldbuilding","plot_structure","character_relations","locations","factions","props",
              "timeline","foreshadowing","adaptation_notes","visual_style","character_visuals",
              "voice_bible","production_constraints"]:
        auto.setdefault(k, [])
    paths.auto_bible_json.write_text(json.dumps(auto, ensure_ascii=False), encoding="utf-8")
    client.patch(f"/api/projects/{pid}/bible", json={"logline": "人工"})
    body = client.get(f"/api/projects/{pid}/bible").json()
    assert body["logline"] == "人工"
```

- [ ] **Step 2: 运行确认失败**

Run: `cd backend && pytest tests/test_api_projects.py tests/test_api_bible.py -v`  
Expected: FAIL

- [ ] **Step 3: 实现 API**

实现要点（完整代码在实现时按此契约编写）：

```python
# backend/src/aivp/api/app.py
from fastapi import FastAPI
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from aivp.config import Settings
from aivp.db import Base
from aivp.api.routes_projects import router as projects_router
from aivp.api.routes_jobs import router as jobs_router
from aivp.api.routes_bible import router as bible_router
from aivp.api.routes_health import router as health_router

def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings()
    settings.data_root.mkdir(parents=True, exist_ok=True)
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    app = FastAPI(title="AIVP Text Layer")
    app.state.settings = settings
    app.state.SessionLocal = SessionLocal
    app.include_router(projects_router, prefix="/api")
    app.include_router(jobs_router, prefix="/api")
    app.include_router(bible_router, prefix="/api")
    app.include_router(health_router, prefix="/api")
    return app
```

`routes_projects.py`：`POST/GET /projects`，`POST /projects/{id}/source` 写入 `ProjectPaths.source_txt`。  
`routes_jobs.py`：`POST /projects/{id}/jobs` 创建 Job 并 `threading.Thread(target=run_job, ...)`；`GET` 返回 status/progress；支持 `resume_from_step`。  
`routes_bible.py`：读 auto+overlay 合并；`PATCH` 写 overlay；`POST /exports` 调 `export_version` 并递增 `Project.export_version`。  
`routes_health.py`：`GET /health/ollama` 调 `OllamaClient.healthy()`。  
统一错误：`{"code","message","details"}`。

另写 `tests/test_api_jobs.py`：创建项目→上传→启动 job（注入 FakeLlm 到 app.state）→轮询至 succeeded。

- [ ] **Step 4: 跑测试**

Run: `cd backend && pytest tests/test_api_projects.py tests/test_api_bible.py tests/test_api_jobs.py -v`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/api backend/tests/test_api_*.py
git commit -m "feat: add FastAPI project, job, bible, and health routes"
```

---

### Task 13: 金样全链路回归（FakeLlm）

**Files:**
- Create: `backend/tests/fixtures/sample_chapter.txt`
- Create: `backend/tests/test_golden_pipeline.py`

- [ ] **Step 1: 写金样测试**

```text
# backend/tests/fixtures/sample_chapter.txt
第一章 山雨欲来

李青云立于青云山门前，手中长剑名为「饮虹」。

第二章 夜宴

青云赴夜宴，遇天机阁密使，埋下一缕剑意伏笔。
```

```python
# backend/tests/test_golden_pipeline.py
from pathlib import Path
from aivp.config import Settings
from aivp.models import Project, Job
from aivp.paths import ProjectPaths
from aivp.llm.fake import FakeLlm
from aivp.pipeline.runner import run_job
from aivp.schemas import REQUIRED_BIBLE_KEYS
from aivp.db import Base
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

def test_golden_two_chapter_pipeline(tmp_path: Path):
    db = tmp_path / "g.db"
    settings = Settings(data_root=tmp_path, db_url=f"sqlite:///{db}")
    engine = create_engine(settings.db_url, connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    session.add(Project(id="g1", name="金样"))
    session.add(Job(id="gj1", project_id="g1", status="queued"))
    session.commit()
    paths = ProjectPaths(tmp_path, "g1")
    paths.ensure()
    fixture = Path(__file__).parent / "fixtures" / "sample_chapter.txt"
    paths.source_txt.write_text(fixture.read_text(encoding="utf-8"), encoding="utf-8")
    llm = FakeLlm(default={
        "characters": [{"name": "李青云", "aliases": ["青云"]}],
        "locations": [{"name": "青云山", "aliases": []}],
        "factions": [{"name": "天机阁", "aliases": []}],
        "props": [{"name": "饮虹", "aliases": []}],
        "events": [{"summary": "关键情节"}],
        "foreshadowing": [{"note": "剑意"}],
        "visual_cues": ["水墨山门"],
        "voice_cues": ["沉稳男声"],
        "adaptation_notes": ["夜宴戏加长"],
    })
    run_job(session, settings, "gj1", llm)
    import json
    bible = json.loads(paths.auto_bible_json.read_text(encoding="utf-8"))
    for k in REQUIRED_BIBLE_KEYS:
        assert k in bible
    assert any(c["name"] == "李青云" for c in bible["characters"])
```

- [ ] **Step 2–4: 红→绿→提交**

Run: `cd backend && pytest tests/test_golden_pipeline.py -v`  
Expected: PASS

```bash
git add backend/tests/fixtures/sample_chapter.txt backend/tests/test_golden_pipeline.py
git commit -m "test: add golden fake-llm pipeline regression"
```

---

### Task 14: Frontend 脚手架 + API client

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/vite.config.ts`
- Create: `frontend/tsconfig.json`
- Create: `frontend/index.html`
- Create: `frontend/src/main.tsx`
- Create: `frontend/src/App.tsx`
- Create: `frontend/src/api/client.ts`
- Create: `frontend/src/__tests__/client.test.ts`

- [ ] **Step 1: 初始化并写 client 测试**

```ts
// frontend/src/__tests__/client.test.ts
import { describe, it, expect, vi } from "vitest";
import { createProject } from "../api/client";

describe("api client", () => {
  it("posts project", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      status: 201,
      json: async () => ({ id: "p1", name: "测" }),
    });
    vi.stubGlobal("fetch", fetchMock);
    const p = await createProject("测");
    expect(p.id).toBe("p1");
    expect(fetchMock).toHaveBeenCalled()
  });
});
```

- [ ] **Step 2: 配置 Vite/Vitest 并使测试失败（无实现）**

`package.json` scripts: `"test": "vitest run"`, `"dev": "vite"`, deps: react、react-dom、vite、vitest、jsdom、@testing-library/react。  
`vite.config.ts` proxy `/api` → `http://127.0.0.1:8000`。

- [ ] **Step 3: 实现 `client.ts` 与空壳页面路由**

```ts
// frontend/src/api/client.ts
const BASE = "";
async function req<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(`${BASE}${path}`, init);
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}
export const createProject = (name: string) =>
  req<{ id: string; name: string }>("/api/projects", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ name }),
  });
export const listProjects = () => req<Array<{ id: string; name: string }>>("/api/projects");
export const getJob = (pid: string, jid: string) =>
  req<{ status: string; current_step: string | null; chunks_done: number; chunks_total: number }>(
    `/api/projects/${pid}/jobs/${jid}`,
  );
export const getBible = (pid: string) => req<Record<string, unknown>>(`/api/projects/${pid}/bible`);
export const patchBible = (pid: string, patch: Record<string, unknown>) =>
  req(`/api/projects/${pid}/bible`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
```

- [ ] **Step 4: 跑前端测试**

Run: `cd frontend && npm i && npm test`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend
git commit -m "chore: scaffold frontend with api client tests"
```

---

### Task 15: 前端页面（列表/流水线/Bible/导出）+ 组件测试

**Files:**
- Create: `frontend/src/pages/ProjectListPage.tsx`
- Create: `frontend/src/pages/PipelinePage.tsx`
- Create: `frontend/src/pages/BiblePage.tsx`
- Create: `frontend/src/pages/ExportPage.tsx`
- Create: `frontend/src/pages/SettingsPage.tsx`
- Create: `frontend/src/__tests__/BiblePage.test.tsx`
- Create: `frontend/src/__tests__/PipelinePage.test.tsx`
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: BiblePage 测试（保存调用 patch）**

```tsx
// frontend/src/__tests__/BiblePage.test.tsx
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { describe, it, expect, vi, beforeEach } from "vitest";
import { BiblePage } from "../pages/BiblePage";
import * as api from "../api/client";

vi.mock("../api/client");

describe("BiblePage", () => {
  beforeEach(() => {
    vi.mocked(api.getBible).mockResolvedValue({ logline: "自动", project_meta: { title: "T" } });
    vi.mocked(api.patchBible).mockResolvedValue({});
  });
  it("saves overlay patch", async () => {
    render(<BiblePage projectId="p1" />);
    await screen.findByDisplayValue("自动");
    fireEvent.change(screen.getByLabelText("logline"), { target: { value: "人工" } });
    fireEvent.click(screen.getByRole("button", { name: "保存" }));
    await waitFor(() => expect(api.patchBible).toHaveBeenCalledWith("p1", { logline: "人工" }));
  });
});
```

- [ ] **Step 2: 运行确认失败**

Run: `cd frontend && npm test`  
Expected: FAIL（页面未实现）

- [ ] **Step 3: 实现页面**

- `ProjectListPage`：列表 + 新建名称  
- `PipelinePage`：上传 input、启动任务、轮询 `getJob` 显示 `current_step` / chunk 进度、失败展示 `error_message`  
- `BiblePage`：左侧 16 节导航，右侧对 `logline` 等关键字段表单编辑 + 保存  
- `ExportPage`：调用 `POST /api/projects/{id}/exports` 并提供下载链接  
- `SettingsPage`：展示默认 Ollama URL/模型（只读或写 localStorage，后端 Settings 仍用环境变量）  
- `App.tsx`：简单 hash/react-router 导航

- [ ] **Step 4: 跑测试**

Run: `cd frontend && npm test`  
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add frontend/src
git commit -m "feat: add console pages for pipeline, bible edit, export"
```

---

### Task 16: README 与本地启动脚说明 + 全量测试

**Files:**
- Create: `README.md`
- Create: `backend/.env.example`

- [ ] **Step 1: 写 README（非测试；含启动命令）**

```markdown
# aiVedioProducer — 文本层 Story Bible

## Backend
cd backend
pip install -e ".[dev]"
uvicorn aivp.api.app:create_app --factory --reload --port 8000

## Frontend
cd frontend
npm i
npm run dev

## Tests
cd backend && pytest -v
cd frontend && npm test
```

- [ ] **Step 2: 全量回归**

Run: `cd backend && pytest -v`  
Expected: 全绿  

Run: `cd frontend && npm test`  
Expected: 全绿

- [ ] **Step 3: Commit**

```bash
git add README.md backend/.env.example
git commit -m "docs: add local run instructions for text-layer MVP"
```

---

## 自检对照（Spec Coverage）

| 规格要求 | 对应任务 |
|---|---|
| Clean→…→Assemble 阶段工件 | Task 3–9, 11 |
| Story Bible 1–16 键 | Task 9, 13 |
| Overlay 编辑不污染 auto | Task 10, 12, 15 |
| 版本化 JSON+MD 导出 | Task 10, 12, 15 |
| 断点续跑 | Task 11–12 |
| Ollama 可插拔 + FakeLlm TDD | Task 6–7, 13 |
| FastAPI + React | Task 12, 14–15 |
| SQLite + 文件系统 | Task 2, 11 |
| 错误/跳过坏块/warnings | Task 7, 11 |
| CI 不依赖真 Ollama | 全部默认测走 FakeLlm；health 可选 |
| 百万字可跑/续跑 | Runner 跳过已存在 extract 文件；chunk 进度字段 |

**占位符扫描：** 无 TBD；Task 12 Step 3 已给出 `create_app` 契约与路由职责清单，实现时按测试补全各 route 文件完整代码。

**类型一致性：** `REQUIRED_BIBLE_KEYS`、阶段名 `01_clean…08_bible`、`ProjectPaths` 字段名在各任务复用同一套。

---

## 执行交接

Plan complete and saved to `docs/superpowers/plans/2026-07-14-text-layer-story-bible.md`. Two execution options:

**1. Subagent-Driven（推荐）** — 每个 Task 派生子代理，任务间审查，迭代快  

**2. Inline Execution** — 本会话按 executing-plans 连续执行，设检查点  

Which approach?
