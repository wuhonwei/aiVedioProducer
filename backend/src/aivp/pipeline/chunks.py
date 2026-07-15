import json
from pathlib import Path


def chunk_chapters(chapters: list[dict], size: int = 4000, overlap: int = 500) -> list[dict]:
    if overlap >= size:
        raise ValueError("overlap_must_be_lt_size")
    out: list[dict] = []
    for ch in chapters:
        text = ch["text"]
        if not text:
            continue
        chapter_base = int(ch.get("start_offset", 0))
        heading_len = int(ch.get("heading_end_offset", chapter_base)) - int(
            ch.get("heading_start_offset", chapter_base)
        )
        # Body starts after heading inside chapter block; chapter text is body-only.
        body_base = int(ch.get("heading_end_offset", chapter_base + heading_len))
        # Skip whitespace between heading and body in original file approximations:
        # use chapter start_offset + (heading width) when available; else 0-based in body.
        start = 0
        idx = 1
        while start < len(text):
            end = min(start + size, len(text))
            piece = text[start:end]
            global_start = body_base + start
            global_end = body_base + end
            out.append(
                {
                    "id": f"{idx:04d}",
                    "chunk_id": f"{ch['id']}_chunk_{idx:04d}",
                    "chapter_id": ch["id"],
                    "chapter_index": ch.get("index", 0),
                    "chapter_title": ch["title"],
                    "index": idx,
                    "chunk_index": idx,
                    "text": piece,
                    "char_count": len(piece),
                    "start_offset": global_start,
                    "end_offset": global_end,
                    "prev_chunk_id": None,
                    "next_chunk_id": None,
                }
            )
            if end >= len(text):
                break
            start = end - overlap
            idx += 1
    # Wire prev/next within full list (and across chapters sequentially).
    for i, c in enumerate(out):
        c["prev_chunk_id"] = out[i - 1]["chunk_id"] if i > 0 else None
        c["next_chunk_id"] = out[i + 1]["chunk_id"] if i + 1 < len(out) else None
    return out


def chunk_report(chunks: list[dict], size: int, overlap: int) -> dict:
    counts = [c.get("char_count", len(c.get("text", ""))) for c in chunks]
    avg = int(sum(counts) / len(counts)) if counts else 0
    return {
        "chunk_count": len(chunks),
        "avg_char_count": avg,
        "chunk_size": size,
        "chunk_overlap": overlap,
        "warnings": [],
    }


def run_chunk(chapters_json: Path, out_jsonl: Path, size: int, overlap: int) -> list[dict]:
    chapters = json.loads(chapters_json.read_text(encoding="utf-8"))
    chunks = chunk_chapters(chapters, size=size, overlap=overlap)
    out_jsonl.parent.mkdir(parents=True, exist_ok=True)
    with out_jsonl.open("w", encoding="utf-8") as f:
        for c in chunks:
            f.write(json.dumps(c, ensure_ascii=False) + "\n")
    report_path = out_jsonl.parent / "chunk_report.json"
    report_path.write_text(
        json.dumps(chunk_report(chunks, size, overlap), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return chunks
