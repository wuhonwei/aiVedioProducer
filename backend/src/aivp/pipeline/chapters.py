import json
import re
from pathlib import Path

# Common Chinese web-novel / book headings.
# Title suffix stays on the same line only (\s would eat the next body line).
HEADING_RE = re.compile(
    r"^(?:"
    r"第[零一二三四五六七八九十百千两0-9]+[章节回卷](?:[ \t]+[^\n]*)?$"
    r"|Chapter\s+\d+(?:[ \t]+[^\n]*)?$"
    r"|卷[零一二三四五六七八九十百千0-9]+(?:[ \t]+[^\n]*)?$"
    r"|序章(?:[ \t]+[^\n]*)?$"
    r"|楔子(?:[ \t]+[^\n]*)?$"
    r"|尾声(?:[ \t]+[^\n]*)?$"
    r"|后记(?:[ \t]+[^\n]*)?$"
    r"|正文$"
    r"|番外[零一二三四五六七八九十百千0-9]*?(?:[ \t]+[^\n]*)?$"
    r")",
    re.MULTILINE | re.IGNORECASE,
)


def _legacy_id(index: int) -> str:
    return f"ch{index:03d}"


def split_chapters(text: str) -> list[dict]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        body = text.strip()
        if not body:
            raise ValueError("chapter_split_empty")
        start = text.find(body)
        end = start + len(body)
        return [
            {
                "id": "chapter_0001",
                "chapter_id": "chapter_0001",
                "legacy_id": "ch001",
                "index": 1,
                "title": "全文",
                "text": body,
                "char_count": len(body),
                "start_offset": start,
                "end_offset": end,
                "heading_start_offset": start,
                "heading_end_offset": start,
                "maybe_unsplit": True,
            }
        ]
    chapters: list[dict] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        title = m.group(0).strip()
        heading_end = m.end()
        body = text[heading_end:end].strip()
        chapter_id = f"chapter_{i+1:04d}"
        chapters.append(
            {
                "id": chapter_id,
                "chapter_id": chapter_id,
                "legacy_id": _legacy_id(i + 1),
                "index": i + 1,
                "title": title,
                "text": body,
                "char_count": len(body),
                "start_offset": start,
                "end_offset": end,
                "heading_start_offset": start,
                "heading_end_offset": heading_end,
                "maybe_unsplit": False,
            }
        )
    return chapters


def chapter_report(chapters: list[dict]) -> dict:
    counts = [c.get("char_count", len(c.get("text", ""))) for c in chapters]
    suspicious = []
    warnings: list[str] = []
    for c in chapters:
        n = c.get("char_count", len(c.get("text", "")))
        cid = c.get("chapter_id") or c.get("id")
        if n < 200:
            suspicious.append(
                {"chapter_id": cid, "reason": "too_short", "char_count": n}
            )
        elif n > 20000:
            suspicious.append(
                {"chapter_id": cid, "reason": "too_long", "char_count": n}
            )
    maybe_unsplit = bool(
        len(chapters) == 1
        and (
            chapters[0].get("maybe_unsplit")
            or chapters[0].get("title") == "全文"
        )
    )
    if maybe_unsplit:
        warnings.append("maybe_unsplit")
        suspicious.append(
            {
                "chapter_id": chapters[0].get("chapter_id") or chapters[0].get("id"),
                "reason": "maybe_unsplit",
                "char_count": counts[0] if counts else 0,
            }
        )
    avg = int(sum(counts) / len(counts)) if counts else 0
    return {
        "chapter_count": len(chapters),
        "avg_char_count": avg,
        "min_char_count": min(counts) if counts else 0,
        "max_char_count": max(counts) if counts else 0,
        "suspicious_chapters": suspicious,
        "maybe_unsplit": maybe_unsplit,
        "warnings": warnings,
    }


def run_chapter_split(
    clean_txt: Path,
    out_json: Path,
    *,
    report_json: Path | None = None,
) -> list[dict]:
    chapters = split_chapters(clean_txt.read_text(encoding="utf-8"))
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = report_json or (out_json.parent / "chapter_report.json")
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(chapter_report(chapters), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return chapters
