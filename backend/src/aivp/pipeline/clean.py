import json
import re
from datetime import datetime, timezone
from pathlib import Path

AD_PATTERNS = [
    re.compile(r"https?://\S+", re.I),
    re.compile(r"www\.\S+", re.I),
    re.compile(r"(最新网址|请收藏本站|手机用户请到|关注微信|加群).*", re.I),
    re.compile(r"(本站域名|记住网址|求推荐票|本章未完).*", re.I),
    re.compile(r"(本书首发|无弹窗|txt下载|TXT下载|手机用户请浏览).*", re.I),
]


def clean_text(text: str) -> tuple[str, dict]:
    removed_lines = 0
    removed_ad_lines = 0
    removed_url_lines = 0
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = "".join(ch for ch in text if ch == "\n" or ch == "\t" or ord(ch) >= 32)
    kept: list[str] = []
    for line in text.split("\n"):
        stripped = line.strip()
        if not stripped:
            kept.append("")
            continue
        is_url = bool(
            re.fullmatch(r"https?://\S+", stripped, flags=re.I)
            or re.fullmatch(r"www\.\S+", stripped, flags=re.I)
        )
        is_ad = any(p.search(stripped) for p in AD_PATTERNS)
        if is_url:
            removed_lines += 1
            removed_url_lines += 1
            continue
        if is_ad and len(stripped) < 120:
            removed_lines += 1
            removed_ad_lines += 1
            continue
        kept.append(line)
    text = "\n".join(kept)
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    if text and not text.endswith("\n"):
        text += "\n"
    report = {
        "removed_lines": removed_lines,
        "removed_ad_lines": removed_ad_lines,
        "removed_url_lines": removed_url_lines,
        "normalized_newlines": True,
        "warnings": [],
    }
    return text, report


def run_clean(source: Path, dest: Path) -> Path:
    raw = source.read_bytes()
    detected = None
    text = None
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            detected = enc
            break
        except UnicodeDecodeError:
            continue
    if text is None or detected is None:
        raise ValueError("unable_to_decode_source")
    cleaned, report = clean_text(text)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(cleaned, encoding="utf-8")
    meta = {
        "novel_id": dest.parent.parent.parent.name if dest.parent.parent.parent else "",
        "title": "未知标题",
        "source_file": str(source.name),
        "detected_encoding": detected,
        "raw_bytes": len(raw),
        "raw_char_count": len(text),
        "clean_char_count": len(cleaned),
        "language": "zh-CN",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    (dest.parent / "metadata.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (dest.parent / "clean_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return dest
