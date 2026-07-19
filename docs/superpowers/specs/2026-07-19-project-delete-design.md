# Project Delete (Hard Delete)

**Date:** 2026-07-19  
**Status:** Implemented  
**Baseline:** current `master` (post keyframe Phase 1)  
**Depends on:** existing `Project` model, `ProjectPaths`, `ProjectListPage`

## Goal

Allow users to permanently delete a project from the project list, removing both the database row and the on-disk project tree under `data/projects/{project_id}/`.

## Decisions

| Topic | Choice |
|-------|--------|
| Delete mode | **Hard delete** (DB + filesystem) |
| Confirmation | **Secondary confirm dialog** (show project name; Cancel / Confirm) |
| Running jobs | **Allow delete** (do not 409); orphaned writers may fail naturally |
| Success response | **200** + `{"deleted": true, "id": "..."}` (optional `warning` if rmtree fails after DB delete) |
| Soft delete / trash | **Out of scope** |
| Batch delete | **Out of scope** |
| Cancel visual/train jobs | **Out of scope** |

## Non-goals

- Soft delete, recycle bin, or restore
- Typing project name to confirm
- Stopping or cancelling in-flight visual/LoRA jobs before delete
- Deleting anything outside `data_root/projects/{project_id}`
- Multi-select / bulk delete

## Backend

### Endpoint

```http
DELETE /api/projects/{project_id}
```

Registered on the existing projects router (`routes_projects.py`).

### Flow

1. Validate `project_id`: reject empty, `..`, `/`, `\` → **400**.
2. Load `Project` from DB; missing → **404**.
3. `db.delete(project)` + `commit`.
4. Resolve `ProjectPaths(settings.data_root, project_id).root` (or equivalent projects dir).
5. If the directory exists, `shutil.rmtree(path)`.
   - If rmtree raises: DB row is already gone; return **200** with `deleted: true` and a `warning` string (e.g. `disk_delete_failed:...`) so the UI does not leave a ghost list entry. Log the exception server-side.
   - If directory does not exist: treat as success (idempotent disk side).
6. Return **200**:

```json
{
  "deleted": true,
  "id": "2ea26d40215d"
}
```

### Safety

- Only delete under `settings.data_root / "projects" / project_id`.
- Never resolve user-controlled paths outside that root (no symlink escape required beyond id validation for v1; id is the short hex from create).

## Frontend

### Client

`frontend/src/api/client.ts`:

```ts
export const deleteProject = (projectId: string) =>
  req<{ deleted: boolean; id: string; warning?: string }>(
    `/api/projects/${encodeURIComponent(projectId)}`,
    { method: "DELETE" },
  );
```

### UI (`ProjectListPage`)

- Each list row: existing open/select control + a **删除** button (`btn-danger` or secondary danger styling).
- Click 删除 → confirm dialog text:

  > 确定删除「{name}」？将永久删除该项目全部数据（文本、视觉资产、LoRA、关键帧等），不可恢复。

  Buttons: **取消** / **确定删除**.
- While deleting: disable actions for that row (or page); show error via existing alert if API fails.
- On success: `refresh()` list.
- If the currently selected app `projectId` equals the deleted id: navigate back to the projects list / clear selection (caller `onSelect` pattern or new `onDeleted` callback from `App.tsx`).

Do not use `window.confirm` if the app already has a modal pattern; otherwise `window.confirm` is acceptable for v1 to ship quickly—prefer a small inline confirm panel in the list card for consistency with existing Chinese UI.

**v1 choice:** use `window.confirm` for minimal surface area, matching “secondary confirmation” without new modal infrastructure. If `window.confirm` is blocked in tests, mock it.

## Testing

| Test | Assert |
|------|--------|
| `test_delete_project_removes_db_and_disk` | create + ensure dirs → DELETE → GET 404, not in list, project dir gone |
| `test_delete_project_not_found` | DELETE missing → 404 |
| `test_delete_project_invalid_id` | id with `..` or slash → 400 |
| `ProjectListPage` (optional) | confirm true → `deleteProject` called; confirm false → not called |

## Acceptance

1. User opens 项目 list, clicks 删除 on a project, cancels → nothing deleted.
2. User confirms → project disappears from list; `data/projects/{id}` is gone.
3. If that project was open, UI returns to project list without a stale chip.
4. API tests pass.

## Follow-ups (deferred)

- Cancel running jobs on delete
- Trash / undo window
- Bulk delete
