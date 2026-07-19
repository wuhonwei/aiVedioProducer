# Project Hard Delete Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let users permanently delete a project (DB row + `data/projects/{id}/`) from the project list with a confirm dialog.

**Architecture:** Add `DELETE /api/projects/{project_id}` on the existing projects router: validate id → delete DB row → `shutil.rmtree` project root. Frontend adds `deleteProject` client helper and a per-row 删除 button on `ProjectListPage` using `window.confirm`; clear app route when the open project is deleted.

**Tech Stack:** FastAPI, SQLAlchemy `Project`, `ProjectPaths`, pytest `TestClient`, React + Vitest, existing `req()` fetch helper.

**Spec:** `docs/superpowers/specs/2026-07-19-project-delete-design.md`

## Global Constraints

- Hard delete only (DB + filesystem under `data_root/projects/{id}`).
- Secondary confirmation via `window.confirm` (v1).
- Do not block delete because of running jobs.
- Success: HTTP **200** + `{"deleted": true, "id": "..."}`; optional `warning` if disk rmtree fails after DB delete.
- Invalid id (`..`, `/`, `\`, empty) → **400**; missing project → **404**.
- Never delete paths outside `settings.data_root / "projects" / project_id`.

## File map

| File | Role |
|------|------|
| `backend/src/aivp/api/routes_projects.py` | `DELETE` endpoint + id validation helper |
| `backend/tests/test_api_projects.py` | API tests for delete / 404 / 400 |
| `frontend/src/api/client.ts` | `deleteProject` |
| `frontend/src/pages/ProjectListPage.tsx` | Delete button + confirm + refresh |
| `frontend/src/App.tsx` | Pass current id + clear route on delete |
| `frontend/src/__tests__/ProjectListPage.test.tsx` | Confirm true/false + API call |

---

### Task 1: Backend DELETE API + tests

**Files:**
- Modify: `backend/src/aivp/api/routes_projects.py`
- Modify: `backend/tests/test_api_projects.py`

**Interfaces:**
- Produces: `DELETE /api/projects/{project_id}` → `{"deleted": true, "id": str, "warning"?: str}`
- Uses: `Project`, `ProjectPaths.root`, `shutil.rmtree`

- [ ] **Step 1: Write failing tests**

Append to `backend/tests/test_api_projects.py`:

```python
import shutil
from pathlib import Path

from fastapi.testclient import TestClient

from aivp.api.app import create_app
from aivp.config import Settings
from aivp.paths import ProjectPaths


def test_delete_project_removes_db_and_disk(tmp_path: Path):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'del.db'}")
    )
    client = TestClient(app)
    pid = client.post("/api/projects", json={"name": "待删"}).json()["id"]
    paths = ProjectPaths(tmp_path, pid)
    paths.ensure()
    (paths.root / "marker.txt").write_text("x", encoding="utf-8")
    assert paths.root.is_dir()

    r = client.delete(f"/api/projects/{pid}")
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["deleted"] is True
    assert body["id"] == pid
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert all(p["id"] != pid for p in client.get("/api/projects").json())
    assert not paths.root.exists()


def test_delete_project_not_found(tmp_path: Path):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'del2.db'}")
    )
    client = TestClient(app)
    r = client.delete("/api/projects/missingproject")
    assert r.status_code == 404


def test_delete_project_invalid_id(tmp_path: Path):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'del3.db'}")
    )
    client = TestClient(app)
    for bad in ["../etc", "a/b", "a\\b", ""]:
        # empty path may 404/405 depending on routing; skip "" if router never matches
        if not bad:
            continue
        r = client.delete(f"/api/projects/{bad}")
        assert r.status_code in (400, 404, 422), (bad, r.status_code, r.text)
```

Note: for `../etc` FastAPI may normalize the path; assert **400** when the handler runs `_validate_project_id`. Prefer calling with id `..` encoded, or test the helper directly plus one HTTP case `ent_.._x` if slash ids are rejected by Starlette. Minimal reliable HTTP invalid case:

```python
def test_delete_project_rejects_dotdot_id(tmp_path: Path):
    app = create_app(
        Settings(data_root=tmp_path, db_url=f"sqlite:///{tmp_path / 'del3.db'}")
    )
    client = TestClient(app)
    r = client.delete("/api/projects/%2e%2e")  # ".."
    assert r.status_code == 400
```

Keep `test_delete_project_not_found` and `test_delete_project_removes_db_and_disk` as the primary suite; include `%2e%2e` invalid-id test.

- [ ] **Step 2: Run tests — expect fail**

Run: `py -3 -m pytest backend/tests/test_api_projects.py::test_delete_project_removes_db_and_disk -q`  
Expected: FAIL (405 Method Not Allowed or 404 — no DELETE route)

- [ ] **Step 3: Implement DELETE in `routes_projects.py`**

Add imports: `import logging`, `import shutil`, `from pathlib import Path` (if needed).

```python
logger = logging.getLogger(__name__)


def _validate_project_id(project_id: str) -> str:
    s = (project_id or "").strip()
    if not s or ".." in s or "/" in s or "\\" in s:
        raise HTTPException(status_code=400, detail=f"invalid_project_id:{project_id!r}")
    return s


@router.delete("/projects/{project_id}")
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> dict[str, Any]:
    pid = _validate_project_id(project_id)
    project = db.get(Project, pid)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {pid} not found")
    db.delete(project)
    db.commit()

    root = ProjectPaths(settings.data_root, pid).root
    warning: str | None = None
    if root.exists():
        try:
            shutil.rmtree(root)
        except OSError as e:
            logger.exception("project disk delete failed: %s", root)
            warning = f"disk_delete_failed:{e}"

    out: dict[str, Any] = {"deleted": True, "id": pid}
    if warning:
        out["warning"] = warning
    return out
```

Also call `_validate_project_id` from `get_project` only if desired — **YAGNI: only on delete** for this task.

- [ ] **Step 4: Run tests — expect pass**

Run: `py -3 -m pytest backend/tests/test_api_projects.py -q`  
Expected: PASS (all tests in file)

- [ ] **Step 5: Commit**

```bash
git add backend/src/aivp/api/routes_projects.py backend/tests/test_api_projects.py
git commit -m "feat(api): hard-delete project removes DB row and disk tree"
```

---

### Task 2: Frontend client + ProjectListPage delete UI

**Files:**
- Modify: `frontend/src/api/client.ts`
- Modify: `frontend/src/pages/ProjectListPage.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/__tests__/ProjectListPage.test.tsx`

**Interfaces:**
- Consumes: `DELETE /api/projects/{id}` JSON from Task 1
- Produces: `deleteProject(projectId: string) => Promise<{deleted: boolean; id: string; warning?: string}>`
- `ProjectListPage` props:

```ts
type Props = {
  onSelect: (projectId: string) => void;
  currentProjectId?: string | null;
  onDeleted?: (projectId: string) => void;
};
```

- [ ] **Step 1: Add client helper**

In `frontend/src/api/client.ts` after `getProject`:

```typescript
export const deleteProject = (projectId: string) =>
  req<{ deleted: boolean; id: string; warning?: string }>(
    `/api/projects/${encodeURIComponent(projectId)}`,
    { method: "DELETE" },
  );
```

- [ ] **Step 2: Wire ProjectListPage**

- Import `deleteProject`.
- Extend props with `currentProjectId?` and `onDeleted?`.
- State: `deletingId: string | null`.
- In each `<li>`, keep the select button; add a sibling delete button:

```tsx
<button
  type="button"
  className="btn btn-danger"
  aria-label={`删除项目 ${p.name}`}
  disabled={creating || deletingId === p.id}
  onClick={(e) => {
    e.stopPropagation();
    void onDelete(p);
  }}
>
  删除
</button>
```

- `onDelete` implementation:

```tsx
const onDelete = async (p: Project) => {
  const ok = window.confirm(
    `确定删除「${p.name}」？将永久删除该项目全部数据（文本、视觉资产、LoRA、关键帧等），不可恢复。`,
  );
  if (!ok) return;
  setDeletingId(p.id);
  setError(null);
  try {
    await deleteProject(p.id);
    await refresh();
    onDeleted?.(p.id);
  } catch (e) {
    setError(e instanceof Error ? e.message : String(e));
  } finally {
    setDeletingId(null);
  }
};
```

Layout: use a `row` flex so open + delete sit side by side without nesting buttons incorrectly (select remains its own button; delete is separate — avoid `<button>` inside `<button>`).

Example structure:

```tsx
<li key={p.id} className="row" style={{ alignItems: "stretch", gap: 8 }}>
  <button type="button" style={{ flex: 1, textAlign: "left" }} onClick={() => onSelect(p.id)}>
    <strong>{p.name}</strong>
    <div style={{ color: "var(--ink-soft)", fontSize: "0.9rem" }}>{p.id}</div>
  </button>
  <button type="button" className="btn btn-danger" ...>删除</button>
</li>
```

- [ ] **Step 3: App.tsx clear route when open project deleted**

```tsx
{page === "list" && (
  <ProjectListPage
    currentProjectId={projectId}
    onSelect={(id) => {
      go("pipeline", id);
    }}
    onDeleted={(id) => {
      if (id === projectId) go("list");
    }}
  />
)}
```

(`go("list")` already clears hash to `#/list`.)

- [ ] **Step 4: Frontend tests**

Extend `frontend/src/__tests__/ProjectListPage.test.tsx`:

```typescript
beforeEach(() => {
  vi.mocked(api.listProjects).mockResolvedValue([
    { id: "p1", name: "仙侠", created_at: null, export_version: 0 },
  ]);
  vi.mocked(api.createProject).mockResolvedValue({ id: "p1", name: "仙侠" });
  vi.mocked(api.deleteProject).mockResolvedValue({ deleted: true, id: "p1" });
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

it("deletes project after confirm", async () => {
  const onDeleted = vi.fn();
  render(<ProjectListPage onSelect={vi.fn()} onDeleted={onDeleted} />);
  await screen.findByText("仙侠");
  fireEvent.click(screen.getByRole("button", { name: "删除项目 仙侠" }));
  await waitFor(() => expect(api.deleteProject).toHaveBeenCalledWith("p1"));
  await waitFor(() => expect(onDeleted).toHaveBeenCalledWith("p1"));
});

it("does not delete when confirm cancelled", async () => {
  vi.spyOn(window, "confirm").mockReturnValue(false);
  render(<ProjectListPage onSelect={vi.fn()} />);
  await screen.findByText("仙侠");
  fireEvent.click(screen.getByRole("button", { name: "删除项目 仙侠" }));
  expect(api.deleteProject).not.toHaveBeenCalled();
});
```

Adjust `Project` type fields to match `client.ts` (`created_at?`, `export_version?`).

Fix existing tests: empty list mock still needed for create tests — split `beforeEach` or override per test (`mockResolvedValueOnce([])` for create cases).

- [ ] **Step 5: Run frontend tests**

Run: `cd frontend && npm test -- --run src/__tests__/ProjectListPage.test.tsx`  
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/api/client.ts frontend/src/pages/ProjectListPage.tsx frontend/src/App.tsx frontend/src/__tests__/ProjectListPage.test.tsx
git commit -m "feat(ui): delete project from list with confirm dialog"
```

---

### Task 3: Verification + mark spec implemented

**Files:**
- Modify: `docs/superpowers/specs/2026-07-19-project-delete-design.md` (Status → Implemented)

- [ ] **Step 1: Run backend + frontend tests**

```bash
py -3 -m pytest backend/tests/test_api_projects.py -q
cd frontend && npm test -- --run src/__tests__/ProjectListPage.test.tsx
```

Expected: all PASS

- [ ] **Step 2: Update spec status**

Set **Status:** Implemented

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-07-19-project-delete-design.md
git commit -m "docs: mark project delete design implemented"
```

---

## Spec coverage checklist

| Spec requirement | Task |
|------------------|------|
| DELETE API hard delete DB + disk | 1 |
| 400 invalid id / 404 missing | 1 |
| 200 + warning on rmtree failure | 1 |
| `deleteProject` client | 2 |
| Confirm dialog + 删除 button | 2 |
| Clear open project route | 2 |
| Tests API + UI | 1–2 |
| Soft delete / job cancel | deferred (non-goals) |

## Plan self-review

- No TBD placeholders; concrete code and commands.
- Response shape consistent: `{deleted, id, warning?}`.
- `req()` requires JSON body → 200 not 204 (matches spec).
- `window.confirm` matches approved v1 confirmation.
