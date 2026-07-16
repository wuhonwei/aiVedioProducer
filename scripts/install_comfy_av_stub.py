"""Install minimal PyAV stub into ComfyUI venv (image-only; no native PyAV)."""
from __future__ import annotations

import argparse
import shutil
import subprocess
from pathlib import Path


def site_packages_dir(venv_python: Path) -> Path:
    out = subprocess.check_output(
        [str(venv_python), "-c", "import site; print('\\n'.join(site.getsitepackages()))"],
        text=True,
    ).strip().splitlines()
    for line in out:
        if line.endswith("site-packages"):
            return Path(line)
    return Path(out[-1])


def write_stub(av_root: Path) -> None:
    if av_root.exists():
        shutil.rmtree(av_root)
    for sub in ["container", "subtitles", "video", "audio", "filter"]:
        (av_root / sub).mkdir(parents=True)

    def w(rel: str, content: str) -> None:
        p = av_root.joinpath(*Path(rel).parts)
        p.write_text(content, encoding="utf-8")

    w(
        "container/__init__.py",
        """class InputContainer:
    format = None
    metadata = {}
    duration = 0
    def __init__(self):
        self.streams = type("Streams", (), {"video": [], "audio": [], "subtitles": []})()
    def demux(self, *args, **kwargs):
        return iter([])
""",
    )
    w(
        "subtitles/stream.py",
        """class SubtitleStream:
    type = "subtitle"
    index = 0
""",
    )
    w("video/reformatter.py", "class ColorRange:\n    pass\n")
    w(
        "audio/resampler.py",
        """class AudioResampler:
    def __init__(self, **kwargs):
        pass
    def resample(self, frame):
        return []
""",
    )
    w(
        "codec.py",
        """class CodecContext:
    @classmethod
    def create(cls, *args, **kwargs):
        return cls()
""",
    )
    w(
        "error.py",
        """class FFmpegError(Exception):
    pass
class InvalidDataError(FFmpegError):
    pass
""",
    )
    w(
        "filter/__init__.py",
        """class Graph:
    def add_buffer(self, **kwargs):
        return _Node()
    def add(self, *args, **kwargs):
        return _Node()
    def configure(self):
        pass
class _Node:
    def link_to(self, other):
        pass
""",
    )
    w(
        "__init__.py",
        '''"""Stub PyAV for ComfyUI image-only startup (no native .pyd)."""
time_base = 1_000_000
class VideoStream:
    type = "video"
    index = 0
    format = None
    codec_context = None
    width = 0
    height = 0
class AudioStream:
    type = "audio"
    index = 0
    codec_context = None
class _StubFormat:
    name = "mp4"
    components = []
class _StubStreams:
    def __init__(self):
        self.video = []
        self.audio = []
        self.subtitles = []
class _StubContainer:
    format = _StubFormat()
    metadata = {}
    duration = 0
    def __init__(self):
        self.streams = _StubStreams()
    def __enter__(self):
        return self
    def __exit__(self, exc_type, exc, tb):
        return False
    def demux(self, stream=None):
        return iter([])
    def add_stream(self, *args, **kwargs):
        return VideoStream()
def open(url=None, mode="r", format=None, **kwargs):
    return _StubContainer()
class VideoFrame:
    width = 0
    height = 0
    pts = 0
    @classmethod
    def from_ndarray(cls, array, format=None):
        return cls()
    def reformat(self, **kwargs):
        return self
class AudioFrame:
    pts = 0
    sample_rate = 44100
    @classmethod
    def from_ndarray(cls, array, format=None, layout=None):
        inst = cls()
        inst.layout = type("Layout", (), {"nb_channels": 2})()
        return inst
''',
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

    subprocess.run([str(python), "-m", "pip", "uninstall", "-y", "av"], capture_output=True)
    sp = site_packages_dir(python)
    av_root = sp / "av"
    write_stub(av_root)
    subprocess.check_call(
        [
            str(python),
            "-c",
            "import av; from av.container import InputContainer; from av.codec import CodecContext",
        ]
    )
    print(f"Installed av stub at {av_root}")


if __name__ == "__main__":
    main()
