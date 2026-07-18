"""Story-driven expression dimensions for Story Bible character cards.

Clusters per-character emotions from enrich/events into independent dims.
Visual layer consumes these; it does not invent the catalog.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

# Canonical key → (label_zh, framing fragment for face sheets)
_CANONICAL: dict[str, tuple[str, str]] = {
    "calm": (
        "平静",
        "calm neutral expression, relaxed brows, soft eyes, closed mouth, "
        "no smile no frown, serene composed face, facial close-up headshot, "
        "complete face forehead to chin, both eyes visible",
    ),
    "smile": (
        "微笑",
        "gentle closed-mouth smile, lips upturned at corners, soft warm eyes, "
        "slight cheek raise, facial close-up headshot, complete face forehead to chin",
    ),
    "happy": (
        "开心",
        "happy joyful expression, big open-mouth grin laugh, teeth visible, "
        "eyes narrowed happily, facial close-up headshot, complete face forehead to chin",
    ),
    "confused": (
        "疑惑",
        "confused puzzled expression, one eyebrow raised, furrowed other brow, "
        "questioning eyes, facial close-up headshot, complete face forehead to chin",
    ),
    "angry": (
        "愤怒",
        "(angry furious expression:1.35), deep frown, furrowed brows, glare stare, "
        "scowling face, no smile, 愤怒咬牙瞪眼皱眉, facial close-up headshot",
    ),
    "sad": (
        "悲伤",
        "(sad sorrowful expression:1.3), teary wet eyes, downturned mouth, "
        "crying face, no smile, 悲伤落泪, facial close-up headshot",
    ),
    "shocked": (
        "震惊",
        "(surprised shocked expression:1.35), wide eyes, raised eyebrows, "
        "open mouth, startled face, 震惊惊讶张嘴, facial close-up headshot",
    ),
    "surprised": (
        "惊讶",
        "(surprised shocked expression:1.35), wide eyes, raised eyebrows, "
        "open mouth O-shape, 惊讶张嘴瞪大眼睛, facial close-up headshot",
    ),
    "shy": (
        "害羞",
        "shy embarrassed expression, blushing cheeks, bashful small smile, "
        "nervous eyes, facial close-up headshot",
    ),
    "warm_care": (
        "关心",
        "warm caring expression, soft gentle eyes, kind concerned look, "
        "tender slight smile, 关心温暖, facial close-up headshot",
    ),
    "fear": (
        "恐惧",
        "fearful scared expression, wide worried eyes, tense brows, "
        "pale anxious face, 恐惧害怕, facial close-up headshot",
    ),
    "determined": (
        "坚定",
        "determined resolute expression, firm mouth, steady eyes, "
        "set jaw, 坚定决心, facial close-up headshot",
    ),
    "tense": (
        "紧张",
        "tense nervous expression, tight lips, alert eyes, "
        "anxious brow, 紧张警惕, facial close-up headshot",
    ),
    "gritted_pain": (
        "忍痛",
        "pain gritted-teeth expression, clenched jaw, furrowed brows, "
        "enduring pain face, 咬牙忍痛, facial close-up headshot",
    ),
}

# Substring / token → canonical key (order matters: first match wins per token)
_SYNONYMS: list[tuple[str, str]] = [
    ("咬牙", "gritted_pain"),
    ("忍痛", "gritted_pain"),
    ("震惊", "shocked"),
    ("吃惊", "shocked"),
    ("骇然", "shocked"),
    ("惊讶", "surprised"),
    ("吃惊", "shocked"),
    ("愤怒", "angry"),
    ("怒", "angry"),
    ("生气", "angry"),
    ("悲伤", "sad"),
    ("伤心", "sad"),
    ("哭", "sad"),
    ("哀", "sad"),
    ("关心", "warm_care"),
    ("温暖", "warm_care"),
    ("慈祥", "warm_care"),
    ("恐惧", "fear"),
    ("害怕", "fear"),
    ("怕", "fear"),
    ("决心", "determined"),
    ("坚定", "determined"),
    ("紧张", "tense"),
    ("警惕", "tense"),
    ("期待", "tense"),
    ("害羞", "shy"),
    ("尴尬", "shy"),
    ("疑惑", "confused"),
    ("困惑", "confused"),
    ("好奇", "confused"),  # curiosity → puzzled look often enough
    ("开心", "happy"),
    ("高兴", "happy"),
    ("欣慰", "happy"),
    ("激动", "happy"),
    ("微笑", "smile"),
    ("笑", "smile"),
    ("平静", "calm"),
]


def normalize_emotion(raw: str) -> str:
    """Map a free-form emotion string to a canonical dim key."""
    text = (raw or "").strip()
    if not text:
        return "calm"
    # Multi-tag strings: resolve the first meaningful segment first.
    segments = [s.strip() for s in re.split(r"[、,/，]+", text) if s.strip()]
    for segment in segments or [text]:
        for token, key in _SYNONYMS:
            if token in segment:
                return key
    # Whole-string fallback
    for token, key in _SYNONYMS:
        if token in text:
            return key
    # Unknown → stable custom key (not forced into legacy 8).
    digest = hashlib.md5(text.encode("utf-8")).hexdigest()[:8]
    return f"custom_{digest}"


def framing_for_key(key: str, *, emotion_raw: str = "") -> str:
    if key in _CANONICAL:
        return _CANONICAL[key][1]
    label = emotion_raw or key
    return (
        f"({label} facial expression:1.3), distinctive mouth eyes and brows for this emotion, "
        "facial close-up headshot, complete face forehead to chin, both eyes visible, "
        "exaggerated readable expression, guofeng anime style"
    )


def label_for_key(key: str, *, emotion_raw: str = "") -> str:
    if key in _CANONICAL:
        return _CANONICAL[key][0]
    return (emotion_raw or key).split("、")[0][:8] or key


def _character_names(character: dict[str, Any]) -> set[str]:
    names = {str(character.get("name") or "").strip()}
    aliases = character.get("aliases") or []
    if isinstance(aliases, list):
        names.update(str(a).strip() for a in aliases)
    cid = str(character.get("id") or "").strip()
    if cid:
        names.add(cid)
    return {n for n in names if n}


def _event_involves(event: dict[str, Any], names: set[str]) -> bool:
    cast = event.get("cast") or event.get("participants") or []
    if isinstance(cast, list):
        for c in cast:
            if isinstance(c, dict):
                n = str(c.get("name") or c.get("id") or "").strip()
            else:
                n = str(c).strip()
            if n in names:
                return True
    summary = str(event.get("summary") or event.get("visual_beat") or "")
    return any(n in summary for n in names if n and not n.startswith("ent_"))


def _calm_dim() -> dict[str, Any]:
    label, framing = _CANONICAL["calm"]
    return {
        "id": "expr_calm",
        "label": label,
        "emotion": "平静",
        "framing": framing,
        "evidence": [],
        "priority": 1,
        "status": "approved",
    }


def build_expression_dims(
    character: dict[str, Any],
    events: list[dict[str, Any]],
    *,
    mentions: list[dict[str, Any]] | None = None,
    max_dims: int = 8,
) -> list[dict[str, Any]]:
    """Cluster story emotions for one character into expression_dims."""
    names = _character_names(character)
    buckets: dict[str, dict[str, Any]] = {}

    def _add(emotion_raw: str, evidence_text: str, source: str, ref: str) -> None:
        key = normalize_emotion(emotion_raw)
        if key == "calm":
            return  # calm is injected separately
        dim_id = f"expr_{key}"
        bucket = buckets.get(dim_id)
        if bucket is None:
            bucket = {
                "id": dim_id,
                "label": label_for_key(key, emotion_raw=emotion_raw),
                "emotion": emotion_raw.strip(),
                "framing": framing_for_key(key, emotion_raw=emotion_raw),
                "evidence": [],
                "priority": 99,
                "status": "proposed",
                "_count": 0,
            }
            buckets[dim_id] = bucket
        bucket["_count"] = int(bucket.get("_count") or 0) + 1
        if evidence_text and len(bucket["evidence"]) < 5:
            bucket["evidence"].append(
                {"text": evidence_text[:200], "source": source, "ref": ref}
            )

    for ev in events or []:
        if not isinstance(ev, dict):
            continue
        if not _event_involves(ev, names):
            continue
        emotion = str(ev.get("emotion") or "").strip()
        if not emotion:
            continue
        # Skip obvious non-emotion enrich noise (soundscape strings).
        if "声" in emotion and "、" not in emotion and len(emotion) > 8:
            continue
        summary = str(ev.get("summary") or ev.get("visual_beat") or emotion)
        ref = str(ev.get("id") or ev.get("event_id") or "")
        _add(emotion, summary, "events_enriched", ref)

    for m in mentions or []:
        if not isinstance(m, dict):
            continue
        n = str(m.get("name") or "").strip()
        if n not in names:
            continue
        emotion = str(m.get("emotion") or "").strip()
        if not emotion:
            continue
        _add(emotion, str(m.get("evidence") or emotion), "character_mention", n)

    ranked = sorted(
        buckets.values(),
        key=lambda d: (-int(d.get("_count") or 0), d["id"]),
    )
    dims: list[dict[str, Any]] = [_calm_dim()]
    for i, raw in enumerate(ranked[: max(0, max_dims)]):
        d = {k: v for k, v in raw.items() if k != "_count"}
        d["priority"] = i + 2
        dims.append(d)
    return dims


def merge_expression_dims(
    existing: list[dict[str, Any]] | None,
    incoming: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    """Merge rebuild results into existing dims without wiping approvals."""
    old = {str(d.get("id")): dict(d) for d in (existing or []) if d.get("id")}
    new = {str(d.get("id")): dict(d) for d in (incoming or []) if d.get("id")}
    out: list[dict[str, Any]] = []

    for dim_id, inc in new.items():
        if dim_id in old:
            prev = old[dim_id]
            status = prev.get("status") or "proposed"
            if status == "rejected":
                merged = {**inc, **prev}
                merged["status"] = "rejected"
            else:
                merged = {**inc, **{k: prev[k] for k in ("status",) if k in prev}}
                # Keep stronger status: approved wins over proposed.
                if prev.get("status") == "approved":
                    merged["status"] = "approved"
                # Append evidence
                ev = list(prev.get("evidence") or [])
                for e in inc.get("evidence") or []:
                    if e not in ev and len(ev) < 5:
                        ev.append(e)
                merged["evidence"] = ev
                if prev.get("framing") and prev.get("status") == "approved":
                    # Preserve human-edited framing on approved dims.
                    merged["framing"] = prev["framing"]
            out.append(merged)
        else:
            out.append(inc)

    for dim_id, prev in old.items():
        if dim_id in new:
            continue
        stale = dict(prev)
        if stale.get("status") != "rejected":
            stale["status"] = "stale"
        out.append(stale)

    # Ensure calm exists.
    if not any(d.get("id") == "expr_calm" for d in out):
        out.insert(0, _calm_dim())

    out.sort(key=lambda d: (int(d.get("priority") or 99), str(d.get("id"))))
    return out
