STAGE_ORDER = [
    "01_clean",
    "02_chapters",
    "03_chunks",
    "04_extract",
    "05_normalize",
    "06_enrich_assets",
    "07_timeline",
    "08_arcs",
    "09_bible",
    "10_shot_script",
]

# Old resume_from_step values from pre-enrich pipelines.
STAGE_ALIASES = {
    "06_timeline": "07_timeline",
    "07_arcs": "08_arcs",
    "08_bible": "09_bible",
}
