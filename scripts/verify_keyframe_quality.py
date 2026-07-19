#!/usr/bin/env python3
"""Automated keyframe generation quality checks against a running API.

Exits non-zero on any assertion failure. Writes JSON report to stdout and
``.superpowers/sdd/keyframe_auto_verify.json``.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REPORT_PATH = ROOT / ".superpowers" / "sdd" / "keyframe_auto_verify.json"

DEFAULT_BASE = "http://127.0.0.1:8000"
DEFAULT_PROJECT = "2ea26d40215d"
PREFERRED_SHOT = "EP001_SCapter_0003_SH001"

FRAMING_TOKENS = (
    "cinematic",
    "medium shot",
    "wide shot",
    "full body",
    "half body",
    "establishing",
)

SHEET_PROMPT_BANS = (
    "国风动画角色定妆",
    "character sheet",
    "turnaround sheet",
)

SHEET_NEG_MARKERS = (
    "character sheet",
    "turnaround sheet",
    "model sheet",
    "reference sheet",
    "定妆",
    "三视图",
)

ENT_ID_RE = re.compile(r"^ent_[A-Za-z0-9_]+$")


def _http_json(
    method: str,
    url: str,
    body: dict[str, Any] | None = None,
    *,
    timeout: float = 600.0,
) -> tuple[int, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            payload = json.loads(raw) if raw else None
            return int(resp.status), payload
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(raw) if raw else {"detail": str(e)}
        except json.JSONDecodeError:
            payload = {"detail": raw or str(e)}
        return int(e.code), payload


def _png_non_empty_heuristic(path: Path) -> dict[str, Any]:
    """Cheap visual sanity: exists, >10KB, not nearly-all-white RGBA."""
    size = path.stat().st_size if path.exists() else 0
    out: dict[str, Any] = {
        "path": str(path.resolve()),
        "exists": path.exists(),
        "size_bytes": size,
        "size_ok": size > 10_240,
        "non_white": False,
        "error": None,
    }
    if not path.exists() or size <= 0:
        return out
    try:
        import struct
        import zlib

        data = path.read_bytes()
        if data[:8] != b"\x89PNG\r\n\x1a\n":
            out["error"] = "not_png"
            return out
        # Parse first IDAT via simple IHDR + sample mid-file bytes for non-white.
        # Prefer Pillow when available.
        try:
            from PIL import Image  # type: ignore

            with Image.open(path) as im:
                im = im.convert("RGB")
                w, h = im.size
                # sample a grid
                samples = []
                for y in (h // 4, h // 2, (3 * h) // 4):
                    for x in (w // 4, w // 2, (3 * w) // 4):
                        samples.append(im.getpixel((x, y)))
                non_white = sum(1 for r, g, b in samples if (r + g + b) < 750) >= 2
                out["non_white"] = non_white
                out["sample_pixels"] = samples
                return out
        except ImportError:
            # Fallback: any byte variance in file body beyond IHDR
            body = data[33:]
            out["non_white"] = len(set(body[:: max(1, len(body) // 200)])) > 8
            # silence unused imports in fallback path
            _ = (struct, zlib)
            return out
    except Exception as e:  # noqa: BLE001
        out["error"] = str(e)
        return out


def _discover_shot_id(base: str, project_id: str, preferred: str) -> str:
    # Prefer known shot; fall back via filesystem shot_script if API has no list.
    backend_data = ROOT / "backend" / "data" / "projects" / project_id
    script = backend_data / "stages" / "10_shot_script" / "shot_script.json"
    if not script.exists():
        # Settings may use repo-relative data/
        alt = ROOT / "data" / "projects" / project_id / "stages" / "10_shot_script" / "shot_script.json"
        script = alt if alt.exists() else script
    if not script.exists():
        return preferred
    doc = json.loads(script.read_text(encoding="utf-8"))
    shots = [s for s in (doc.get("shots") or []) if isinstance(s, dict)]
    ids = {str(s.get("shot_id") or "") for s in shots}
    if preferred in ids:
        return preferred
    for s in shots:
        ar = s.get("asset_refs") if isinstance(s.get("asset_refs"), dict) else {}
        cast = (
            ar.get("characters")
            or s.get("cast")
            or s.get("characters")
            or (
                (s.get("assets_required") or {}).get("characters")
                if isinstance(s.get("assets_required"), dict)
                else None
            )
        )
        if cast:
            return str(s.get("shot_id"))
    return preferred


def _candidate_paths(project_id: str, shot_id: str, files: list[str]) -> list[Path]:
    roots = [
        ROOT / "backend" / "data" / "projects" / project_id / "keyframes" / shot_id / "candidates",
        ROOT / "data" / "projects" / project_id / "keyframes" / shot_id / "candidates",
    ]
    out: list[Path] = []
    for fname in files:
        found = None
        for root in roots:
            p = root / fname
            if p.exists():
                found = p
                break
        out.append(found or (roots[0] / fname))
    return out


def _lora_ready_character_ids(project_id: str, character_ids: list[str]) -> list[str]:
    ready: list[str] = []
    for cid in character_ids:
        for base in (
            ROOT / "backend" / "data" / "projects" / project_id / "visual" / "characters" / cid,
            ROOT / "data" / "projects" / project_id / "visual" / "characters" / cid,
        ):
            profile_path = base / "profile.json"
            if not profile_path.exists():
                continue
            try:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if profile.get("lora_ready"):
                ready.append(cid)
            break
    return ready


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else DEFAULT_BASE).rstrip("/")
    project_id = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_PROJECT
    preferred = sys.argv[3] if len(sys.argv) > 3 else PREFERRED_SHOT

    failures: list[str] = []
    report: dict[str, Any] = {
        "base": base,
        "project_id": project_id,
        "shot_id": None,
        "http_status": None,
        "assertions": {},
        "generation": None,
        "pngs": [],
        "failures": failures,
        "ok": False,
    }

    # Health
    status, _ = _http_json("GET", f"{base}/api/projects", timeout=15)
    if status != 200:
        failures.append(f"api_projects_status:{status}")
        report["assertions"]["api_up"] = False
        return _finish(report, 1)
    report["assertions"]["api_up"] = True

    shot_id = _discover_shot_id(base, project_id, preferred)
    report["shot_id"] = shot_id

    url = f"{base}/api/projects/{project_id}/keyframes/{shot_id}/generate"
    status, payload = _http_json(
        "POST",
        url,
        {"force": True, "count": 2, "use_location_lora": False},
        timeout=900,
    )
    report["http_status"] = status
    report["response_keys"] = list(payload.keys()) if isinstance(payload, dict) else type(payload).__name__

    if status != 200:
        failures.append(f"generate_http:{status}:{payload}")
        report["assertions"]["http_200"] = False
        return _finish(report, 1)
    report["assertions"]["http_200"] = True

    if not isinstance(payload, dict):
        failures.append("response_not_object")
        return _finish(report, 1)

    generation = payload.get("generation") if isinstance(payload.get("generation"), dict) else {}
    report["generation"] = generation

    character_ids = [str(x) for x in (generation.get("character_ids") or [])]
    ids_ok = bool(character_ids) and all(ENT_ID_RE.match(cid) for cid in character_ids)
    # Also reject obvious Chinese / non-ascii names (no Han script in id)
    if any(re.search(r"[\u4e00-\u9fff]", cid) for cid in character_ids):
        ids_ok = False
    report["assertions"]["character_ids_ent_style"] = ids_ok
    if not ids_ok:
        failures.append(f"character_ids_not_ent_style:{character_ids}")

    loras = generation.get("loras") or []
    ready_ids = _lora_ready_character_ids(project_id, character_ids)
    if ready_ids:
        loras_ok = isinstance(loras, list) and len(loras) >= 1
        report["assertions"]["loras_present_when_ready"] = loras_ok
        report["lora_ready_character_ids"] = ready_ids
        if not loras_ok:
            failures.append(f"loras_missing_despite_ready:{ready_ids}:{loras}")
    else:
        report["assertions"]["loras_present_when_ready"] = True
        report["lora_ready_character_ids"] = []

    prompt = str(generation.get("prompt") or "")
    prompt_l = prompt.lower()
    framing_ok = any(tok in prompt_l for tok in FRAMING_TOKENS)
    report["assertions"]["prompt_has_framing"] = framing_ok
    if not framing_ok:
        failures.append("prompt_missing_framing_tokens")

    sheet_in_prompt = any(b.lower() in prompt_l if b.isascii() else b in prompt for b in SHEET_PROMPT_BANS)
    report["assertions"]["prompt_no_sheet_language"] = not sheet_in_prompt
    if sheet_in_prompt:
        failures.append("prompt_contains_sheet_language")

    negative = str(generation.get("negative") or "")
    neg_l = negative.lower()
    neg_has_sheet_ban = any(
        (m.lower() in neg_l) if m.isascii() else (m in negative) for m in SHEET_NEG_MARKERS
    )
    prompt_no_dingzhuang = "定妆" not in prompt
    sheet_neg_ok = neg_has_sheet_ban or prompt_no_dingzhuang
    report["assertions"]["negative_sheet_bans_or_no_dingzhuang"] = sheet_neg_ok
    if not sheet_neg_ok:
        failures.append("negative_missing_sheet_bans_and_prompt_has_dingzhuang")

    cand_files = [
        str(c.get("file"))
        for c in (payload.get("candidates") or [])
        if isinstance(c, dict) and c.get("file")
    ]
    paths = _candidate_paths(project_id, shot_id, cand_files)
    png_meta = [_png_non_empty_heuristic(p) for p in paths]
    report["pngs"] = png_meta
    files_ok = len(png_meta) >= 1 and all(m["exists"] and m["size_ok"] for m in png_meta)
    report["assertions"]["candidate_pngs_exist_gt_10kb"] = files_ok
    if not files_ok:
        failures.append(f"candidate_pngs_bad:{png_meta}")

    # Soft visual heuristic (reported; hard-fail only if all look empty/white)
    if png_meta and all(m.get("exists") and m.get("size_ok") for m in png_meta):
        if all(m.get("non_white") is False and not m.get("error") for m in png_meta):
            failures.append("pngs_appear_blank_or_white")
            report["assertions"]["pngs_non_white"] = False
        else:
            report["assertions"]["pngs_non_white"] = any(m.get("non_white") for m in png_meta)

    report["prompt_full"] = prompt
    report["negative_full"] = negative
    report["loras"] = loras
    report["ok"] = not failures
    return _finish(report, 0 if not failures else 1)


def _finish(report: dict[str, Any], code: int) -> int:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(report, ensure_ascii=False, indent=2)
    REPORT_PATH.write_text(text, encoding="utf-8")
    print(text)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
