#!/usr/bin/env python3
"""On agent stop: if the working tree is dirty, commit and push to origin."""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        args,
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
        encoding="utf-8",
        errors="replace",
    )


def main() -> int:
    # Consume hook stdin JSON (required by Cursor hooks protocol).
    try:
        sys.stdin.read()
    except Exception:
        pass

    if not (ROOT / ".git").exists():
        print("{}")
        return 0

    status = run(["git", "status", "--porcelain"])
    if status.returncode != 0 or not (status.stdout or "").strip():
        print("{}")
        return 0

    run(["git", "add", "-A"])
    staged = run(["git", "diff", "--cached", "--quiet"])
    if staged.returncode == 0:
        print("{}")
        return 0

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    msg = f"chore: auto-sync from Cursor ({stamp})"
    commit = run(["git", "commit", "-m", msg])
    if commit.returncode != 0:
        # Nothing to commit or hook blocked — fail open.
        print("{}")
        return 0

    push = run(["git", "push", "-u", "origin", "HEAD"])
    if push.returncode != 0:
        # Fail open: do not block the agent stop; surface hint via empty follow-up.
        print("{}")
        return 0

    print("{}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
