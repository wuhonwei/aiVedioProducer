from typing import Any
from pydantic import BaseModel, Field


class NamedEntity(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)


class ChunkExtract(BaseModel):
    characters: list[NamedEntity] = Field(default_factory=list)
    locations: list[NamedEntity] = Field(default_factory=list)
    factions: list[NamedEntity] = Field(default_factory=list)
    props: list[NamedEntity] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    foreshadowing: list[dict[str, Any]] = Field(default_factory=list)
    visual_cues: list[str] = Field(default_factory=list)
    voice_cues: list[str] = Field(default_factory=list)
    adaptation_notes: list[str] = Field(default_factory=list)


REQUIRED_BIBLE_KEYS = [
    "project_meta", "logline", "worldbuilding", "plot_structure", "characters",
    "character_relations", "locations", "factions", "props", "timeline",
    "foreshadowing", "adaptation_notes", "visual_style", "character_visuals",
    "voice_bible", "production_constraints",
]
