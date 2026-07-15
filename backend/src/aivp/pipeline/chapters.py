import json
import re
from pathlib import Path

# Common Chinese web-novel / book headings.
HEADING_RE = re.compile(
    r"^(?:"
    r"第[零一二三四五六七八九十百千两0-9]+[章节回卷](?:\s+.*)?$"
    r"|Chapter\s+\d+(?:\s+.*)?$"
    r"|卷[零一二三四五六七八九十百千0-9]+(?:\s+.*)?$"
    r"|序章(?:\s+.*)?$"
    r"|楔子(?:\s+.*)?$"
    r"|尾声(?:\s+.*)?$"
    r"|正文$"
    r"|番外[零一二三四五六七八九十百千0-9]*?(?:\s+.*)?$"
    r")",
    re.MULTILINE | re.IGNORECASE,
)


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
                "id": "ch001",
                "index": 1,
                "title": "全文",
                "text": body,
                "char_count": len(body),
                "start_offset": start,
                "end_offset": end,
                "heading_start_offset": start,
                "heading_end_offset": start,
            }
        ]
    chapters: list[dict] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end]
        title = m.group(0).strip()
        heading_end = m.end()
        body = text[heading_end:end].strip()
        # Prefer body start offset inside cleaned text for evidence chain.
        body_start = heading_end
        while body_start < end and text[body_start] in "\r\n \t":
            body_start += 1
        body_end = body_start + len(body) if body else heading_end
        chapters.append(
            {
                "id": f"ch{i+1:03d}",
                "index": i + 1,
                "title": title,
                "text": body,
                "char_count": len(body),
                "start_offset": start,
                "end_offset": end,
                "heading_start_offset": start,
                "heading_end_offset": heading_end,
            }
        )
        _ = body_end  # reserved for future precise body_end on cleaned file
    return chapters


def chapter_report(chapters: list[dict]) -> dict:
    counts = [c.get("char_count", len(c.get("text", ""))) for c in chapters]
    suspicious = []
    for c in chapters:
        n = c.get("char_count", len(c.get("text", "")))
        if n < 200:
            suspicious.append(
                {"chapter_id": c["id"], "reason": "too_short", "char_count": n}
            )
        elif n > 20000:
            suspicious.append(
                {"chapter_id": c["id"], "reason": "too_long", "char_count": n}
            )
    avg = int(sum(counts) / len(counts)) if counts else 0
    return {
        "chapter_count": len(chapters),
        "avg_char_count": avg,
        "min_char_count": min(counts) if counts else 0,
        "max_char_count": max(counts) if counts else 0,
        "suspicious_chapters": suspicious,
    }


def run_chapter_split(clean_txt: Path, out_json: Path) -> list[dict]:
    chapters = split_chapters(clean_txt.read_text(encoding="utf-8"))
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")
    report_path = out_json.parent / "chapter_report.json"
    report_path.write_text(
        json.dumps(chapter_report(chapters), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return chapters
