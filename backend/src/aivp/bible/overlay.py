import copy
from typing import Any


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
