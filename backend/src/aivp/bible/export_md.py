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

PACK_MD_FILES = [
    ("00_project.md", "project_meta"),
    ("01_logline_and_theme.md", "logline"),
    ("02_world_bible.md", "worldbuilding"),
    ("03_plot_arcs.md", "plot_structure"),
    ("04_character_bible.md", "characters"),
    ("05_relationships.md", "character_relations"),
    ("06_location_bible.md", "locations"),
    ("07_organizations.md", "factions"),
    ("08_items.md", "props"),
    ("09_timeline.md", "timeline"),
    ("10_foreshadowing.md", "foreshadowing"),
    ("11_adaptation_notes.md", "adaptation_notes"),
    ("12_visual_style_bible.md", "visual_style"),
    ("13_voice_bible.md", "voice_bible"),
    ("14_generation_constraints.md", "production_constraints"),
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


def export_markdown_pack(pack_dir: Path, bible: dict) -> Path:
    pack_dir.mkdir(parents=True, exist_ok=True)
    json_dir = pack_dir / "json"
    json_dir.mkdir(parents=True, exist_ok=True)
    (json_dir / "story_bible.merged.json").write_text(
        json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    for key in ("characters", "locations", "timeline"):
        (json_dir / f"{key}.json").write_text(
            json.dumps(bible.get(key), ensure_ascii=False, indent=2), encoding="utf-8"
        )
    for filename, key in PACK_MD_FILES:
        title = next((t for k, t in SECTION_TITLES if k == key), key)
        body = [
            f"# {title}",
            "",
            "```json",
            json.dumps(bible.get(key), ensure_ascii=False, indent=2),
            "```",
            "",
        ]
        (pack_dir / filename).write_text("\n".join(body), encoding="utf-8")
    return pack_dir


def export_version(exports_dir: Path, bible: dict, version: int) -> dict[str, Path]:
    exports_dir.mkdir(parents=True, exist_ok=True)
    stem = f"story_bible.v{version:03d}"
    json_path = exports_dir / f"{stem}.json"
    md_path = exports_dir / f"{stem}.md"
    json_path.write_text(json.dumps(bible, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(bible_to_markdown(bible), encoding="utf-8")
    pack_dir = exports_dir / f"{stem}_pack"
    export_markdown_pack(pack_dir, bible)
    return {"json": json_path, "md": md_path, "pack": pack_dir}
