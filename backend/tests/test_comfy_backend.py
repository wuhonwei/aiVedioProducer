import json
from pathlib import Path

import httpx

from aivp.visual.image_backend import (
    ComfyImageBackend,
    build_sdxl_txt2img_workflow,
)


def test_build_sdxl_workflow_embeds_checkpoint_and_prompts():
    wf = build_sdxl_txt2img_workflow(
        checkpoint="Guofeng4.2XL.safetensors",
        prompt="lin_aivp, 少年青衣",
        negative="blurry",
        seed=42,
    )
    assert wf["4"]["inputs"]["ckpt_name"] == "Guofeng4.2XL.safetensors"
    assert wf["6"]["inputs"]["text"] == "lin_aivp, 少年青衣"
    assert wf["7"]["inputs"]["text"] == "blurry"
    assert wf["3"]["inputs"]["seed"] == 42


def test_comfy_generate_downloads_image(tmp_path: Path, monkeypatch):
    dest = tmp_path / "out.png"
    png_bytes = b"\x89PNG\r\n\x1a\n" + b"fake"

    class FakeResponse:
        def __init__(self, status_code=200, payload=None, content=b""):
            self.status_code = status_code
            self._payload = payload
            self.content = content
            self.text = json.dumps(payload) if payload is not None else ""

        def json(self):
            return self._payload

    calls = {"n": 0}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            if url.endswith("/system_stats"):
                return FakeResponse(200, {})
            if "/history/" in url:
                return FakeResponse(
                    200,
                    {
                        "pid1": {
                            "outputs": {
                                "9": {
                                    "images": [
                                        {
                                            "filename": "aivp_00001_.png",
                                            "subfolder": "",
                                            "type": "output",
                                        }
                                    ]
                                }
                            }
                        }
                    },
                )
            if url.endswith("/view"):
                return FakeResponse(200, content=png_bytes)
            return FakeResponse(404)

        def post(self, url, json=None):
            calls["n"] += 1
            assert url.endswith("/prompt")
            assert json["prompt"]["4"]["inputs"]["ckpt_name"] == "Guofeng4.2XL.safetensors"
            return FakeResponse(200, {"prompt_id": "pid1"})

    monkeypatch.setattr(httpx, "Client", FakeClient)
    backend = ComfyImageBackend("http://127.0.0.1:8188", "Guofeng4.2XL.safetensors")
    out = backend.generate(prompt="test", negative="bad", dest=dest, seed=1)
    assert out.exists()
    assert out.read_bytes() == png_bytes
    assert calls["n"] == 1


def test_comfy_requires_checkpoint(tmp_path: Path, monkeypatch):
    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def get(self, url, params=None):
            return type("R", (), {"status_code": 200})()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    backend = ComfyImageBackend("http://127.0.0.1:8188", "")
    try:
        backend.generate(prompt="x", negative="", dest=tmp_path / "a.png", seed=0)
        raised = False
    except RuntimeError as e:
        raised = str(e).startswith("comfy_checkpoint_empty")
    assert raised
