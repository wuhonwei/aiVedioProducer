from pathlib import Path


def clean_text(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text.lstrip("\ufeff")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    while "\n\n\n" in text:
        text = text.replace("\n\n\n", "\n\n")
    if text and not text.endswith("\n"):
        text += "\n"
    return text


def run_clean(source: Path, dest: Path) -> Path:
    raw = source.read_bytes()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        raise ValueError("unable_to_decode_source")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(clean_text(text), encoding="utf-8")
    return dest
