import json
from pathlib import Path


def chunk_chapters(chapters: list[dict], size: int = 1200, overlap: int = 150) -> list[dict]:
    if overlap >= size:
        raise ValueError("overlap_must_be_lt_size")
    out: list[dict] = []
    for ch in chapters:
        text = ch["text"]
        if not text:
            continue
        start = 0
        idx = 1
        while start < len(text):
            end = min(start + size, len(text))
            piece = text[start:end]
            out.append({
                "id": f"{idx:04d}",
                "chapter_id": ch["id"],
                "chapter_title": ch["title"],
                "index": idx,
                "text": piece,
            })
            if end >= len(text):
                break
            start = end - overlap
            idx += 1
    return out


def run_chunk(chapters_json: Path, out_jsonl: Path, size: int, overlap: int) -> list[dict]:
    chapters = json.loads(chapters_json.read_text(encoding="utf-8"))
    chunks = chunk_chapters(chapters, size=size, overlap=overlap)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    return chunks
