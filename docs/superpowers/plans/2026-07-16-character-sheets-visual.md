# Character sheets Visual UI — Implementation Plan

> **For agentic workers:** Implement task-by-task; mark checkboxes; run tests after each backend task.

**Goal:** Portrait-safe t2i + sheets job + zoom/delete UI.

**Tech:** FastAPI visual routes, Comfy workflow, React VisualPage.

## Task 1: Prompt helpers + Comfy size/LoRA

Files: `backend/src/aivp/visual/prompts.py` (new), `image_backend.py`, `t2i.py`, `candidates.py`, tests

## Task 2: Sheets generator + paths/status + API delete/sheets

Files: `sheets.py`, `paths.py`, `profiles.py`, `routes_visual.py`, tests

## Task 3: Frontend client + VisualPage

Files: `client.ts`, `VisualPage.tsx`
