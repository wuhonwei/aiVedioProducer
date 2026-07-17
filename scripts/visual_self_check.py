"""CLI: generate + vision-judge character images, auto-tune until pass rate OK.

Example:
  cd backend
  python ../scripts/visual_self_check.py --project 9af4a38fa154 --characters ent_0001 --rounds 3
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND / "src"))

from aivp.config import Settings  # noqa: E402
from aivp.llm.ollama_vision_client import OllamaVisionClient  # noqa: E402
from aivp.visual.image_backend import get_image_backend  # noqa: E402
from aivp.visual.paths import VisualPaths  # noqa: E402
from aivp.visual.self_check import (  # noqa: E402
    evaluate_character_images,
    run_self_check_loop,
)
from aivp.visual.profiles import load_major_characters  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Visual self-check with local vision LLM")
    parser.add_argument("--project", required=True, help="Project id (e.g. 9af4a38fa154)")
    parser.add_argument("--characters", default="", help="Comma-separated character ids")
    parser.add_argument("--rounds", type=int, default=None)
    parser.add_argument("--pass-rate", type=float, default=None)
    parser.add_argument("--candidate-count", type=int, default=4)
    parser.add_argument(
        "--judge-only",
        action="store_true",
        help="Only judge existing images; do not regenerate",
    )
    parser.add_argument("--no-apply", action="store_true", help="Do not write qa_tuning.json")
    args = parser.parse_args()

    settings = Settings()
    vision = OllamaVisionClient(settings.ollama_base_url, settings.ollama_vision_model)
    if not vision.model_available():
        print(
            f"Vision model not available: {settings.ollama_vision_model}\n"
            f"Run: ollama pull {settings.ollama_vision_model}",
            file=sys.stderr,
        )
        return 2

    vpaths = VisualPaths(settings.data_root, args.project)
    vpaths.ensure()
    ids = [x.strip() for x in args.characters.split(",") if x.strip()] or None
    threshold = (
        float(args.pass_rate)
        if args.pass_rate is not None
        else float(settings.visual_qa_pass_rate)
    )
    rounds = int(args.rounds) if args.rounds is not None else int(settings.visual_qa_max_rounds)

    if args.judge_only:
        majors = load_major_characters(vpaths)
        if ids:
            wanted = set(ids)
            majors = [c for c in majors if str(c.get("id") or "") in wanted]
        reports = []
        for ch in majors:
            reports.append(
                evaluate_character_images(vpaths, ch, vision, include_candidates=True, include_sheets=True)
            )
        out = {
            "mode": "judge_only",
            "project": args.project,
            "pass_rate_threshold": threshold,
            "reports": [
                {
                    "character_id": r["character_id"],
                    "name": r.get("name"),
                    "pass_rate": r.get("pass_rate"),
                    "pass_rate_by_kind": r.get("pass_rate_by_kind"),
                    "failure_tags": r.get("failure_tags"),
                    "pass_count": r.get("pass_count"),
                    "count": r.get("count"),
                }
                for r in reports
            ],
        }
        path = vpaths.root / "qa_self_check_report.json"
        path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(out, ensure_ascii=False, indent=2))
        print(f"Wrote {path}")
        rates = [float(r.get("pass_rate") or 0) for r in reports if r.get("pass_rate") is not None]
        avg = sum(rates) / len(rates) if rates else 0.0
        return 0 if avg >= threshold else 1

    backend = get_image_backend(settings)
    summary = run_self_check_loop(
        vpaths,
        backend,
        vision,
        character_ids=ids,
        pass_rate_threshold=threshold,
        max_rounds=rounds,
        candidate_count=int(args.candidate_count),
        apply_patches=not args.no_apply,
    )
    print(json.dumps(
        {
            "final_pass_rate": summary.get("final_pass_rate"),
            "final_passed": summary.get("final_passed"),
            "rounds": [
                {
                    "round": r["round"],
                    "pass_rate": r["pass_rate"],
                    "passed": r["passed"],
                    "patches": {
                        k: v
                        for k, v in (r.get("patches") or {}).items()
                        if k not in {"reason_tags"}
                    },
                }
                for r in summary.get("rounds") or []
            ],
            "report_path": summary.get("report_path"),
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if summary.get("final_passed") else 1


if __name__ == "__main__":
    raise SystemExit(main())
