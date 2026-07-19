"""Bypass Windows Smart App Control blocks on unsigned SciPy .pyd files.

ComfyUI startup does `import scipy.stats`, which pulls scipy.interpolate and
loads `_rbfinterp_pythran*.pyd`. SAC often blocks that DLL. Image-only Comfy
only needs `scipy.stats.beta.ppf` (beta scheduler), not RBF interpolation.

This renames the blocked .pyd and installs a pure-Python stub so imports succeed.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path

STUB_RBF_PYTHRAN = '''\
"""Pure-Python stub for SciPy RBF pythran extension (Smart App Control bypass).

ComfyUI image workflows do not call these; they exist so `import scipy.stats` works.
"""


def _build_system(*args, **kwargs):
    raise NotImplementedError(
        "scipy.interpolate RBF pythran is stubbed (Smart App Control). "
        "RBFInterpolator is unavailable; Comfy image sampling does not need it."
    )


def _build_evaluation_coefficients(*args, **kwargs):
    raise NotImplementedError(
        "scipy.interpolate RBF pythran is stubbed (Smart App Control)."
    )


def _polynomial_matrix(*args, **kwargs):
    raise NotImplementedError(
        "scipy.interpolate RBF pythran is stubbed (Smart App Control)."
    )
'''


def site_packages_dir(venv_python: Path) -> Path:
    out = subprocess.check_output(
        [str(venv_python), "-c", "import site; print('\\n'.join(site.getsitepackages()))"],
        text=True,
    ).strip().splitlines()
    for line in out:
        if line.endswith("site-packages"):
            return Path(line)
    return Path(out[-1])


def neutralize_pyd(path: Path) -> None:
    blocked = path.with_suffix(path.suffix + ".sac-blocked")
    if blocked.exists():
        blocked.unlink()
    path.rename(blocked)
    print(f"Renamed blocked native module: {path.name} -> {blocked.name}")


def patch_rbfinterp_pythran(sp: Path) -> bool:
    interp = sp / "scipy" / "interpolate"
    if not interp.is_dir():
        print("scipy.interpolate not found; skip")
        return False

    changed = False
    for pyd in interp.glob("_rbfinterp_pythran*.pyd"):
        neutralize_pyd(pyd)
        changed = True

    stub = interp / "_rbfinterp_pythran.py"
    stub.write_text(STUB_RBF_PYTHRAN, encoding="utf-8")
    print(f"Wrote stub: {stub}")
    return True


def verify(venv_python: Path) -> None:
    subprocess.check_call(
        [
            str(venv_python),
            "-c",
            "import scipy.stats; print('scipy.stats OK', scipy.stats.beta.ppf(0.5, 2, 2))",
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--comfy-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "tools" / "ComfyUI",
    )
    args = parser.parse_args()
    comfy = args.comfy_root.resolve()
    python = comfy / ".venv" / "Scripts" / "python.exe"
    if not python.is_file():
        raise SystemExit(f"Comfy venv python not found: {python}")

    sp = site_packages_dir(python)
    patch_rbfinterp_pythran(sp)
    verify(python)
    print("Smart App Control scipy stub installed.")


if __name__ == "__main__":
    main()
