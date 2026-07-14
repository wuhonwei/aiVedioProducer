import json
import re
from pathlib import Path

HEADING_RE = re.compile(
    r"^(第[零一二三四五六七八九十百千0-9]+章\s*.+)$",
    re.MULTILINE,
)


def split_chapters(text: str) -> list[dict]:
    matches = list(HEADING_RE.finditer(text))
    if not matches:
        body = text.strip()
        if not body:
            raise ValueError("chapter_split_empty")
        return [{"id": "ch001", "index": 1, "title": "全文", "text": body}]
    chapters: list[dict] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        title = m.group(1).strip()
        body = block[len(title):].strip()
        chapters.append({
            "id": f"ch{i+1:03d}",
            "index": i + 1,
            "title": title,
            "text": body,
        })
    return chapters


def run_chapter_split(clean_txt: Path, out_json: Path) -> list[dict]:
    chapters = split_chapters(clean_txt.read_text(encoding="utf-8"))
    out_json.parent.mkdir(parents=True, exist_ok=True)
    out_json.write_text(json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8")
    return chapters
