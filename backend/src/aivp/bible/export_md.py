import json
from pathlib import Path

SECTION_TITLES = [
    ("project_meta", "1. 项目元信息"),
    ("logline", "2. 故事一句话概括"),
    ("worldbuilding", "3. 世界观设定"),
    ("plot_structure", "4. 主线剧情 / 篇章结构"),
    ("characters", "5. 主要角色 Bible"),
    ("character_relations", "6. 角色关系"),
    ("locations", "7. 地点 / 场景 Bible"),
    ("factions", "8. 组织 / 阵营 / 势力"),
    ("props", "9. 重要道具 / 法宝 / 物件"),
    ("timeline", "10. 事件时间线"),
    ("foreshadowing", "11. 伏笔 / 悬念 / 回收"),
    ("adaptation_notes", "12. 影视化改编信息"),
    ("visual_style", "13. 视觉风格 Bible"),
    ("character_visuals", "14. 角色视觉设定"),
    ("voice_bible", "15. 声音设定 Voice Bible"),
    ("production_constraints", "16. 分镜/资产生产约束"),
]


def bible_to_markdown(bible: dict) -> str:
    lines = ["# Story Bible", ""]
    for key, title in SECTION_TITLES:
        lines.append(f"## {title}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(bible.get(key), ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    return "\n".join(lines)


def export_version(exports_dir: Path, bible: dict, version: int) -> dict[str, Path]:
    exports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"story_bible.v{version:03d}"
    json_path = exports_dir / f"{stem}.json"
    md_path = exports_dir / f"{stem}.md"
    json_path.write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(bible_to_markdown(bible), encoding="utf-8")
    return {"json": json_path, "md": md_path}
