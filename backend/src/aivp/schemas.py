from typing import Any
from pydantic import BaseModel, Field


class NamedEntity(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    evidence: str = ""
    identity_hint: str = ""


class EvidenceFact(BaseModel):
    fact: str = ""
    evidence: str = ""
    confidence: float = 0.0


class CharacterMention(BaseModel):
    name: str
    aliases: list[str] = Field(default_factory=list)
    identity_hint: str = ""
    appearance: list[EvidenceFact] = Field(default_factory=list)
    personality: list[EvidenceFact] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    emotion: str = ""
    evidence: str = ""


class EventFact(BaseModel):
    summary: str
    evidence: str = ""
    participants: list[str] = Field(default_factory=list)
    location: str = ""
    time_hint: str = ""
    cause: str = ""
    process: str = ""
    result: str = ""
    importance: float = 0.0
    visual_score: float = 0.0


class VisualCandidate(BaseModel):
    scene: str = ""
    visual_score: float = 0.0
    reason: str = ""
    suggested_shots: list[str] = Field(default_factory=list)
    difficulty: str = ""
    evidence: str = ""


class ChunkQuality(BaseModel):
    json_repaired: bool = False
    missing_evidence_count: int = 0
    low_confidence_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class ChunkExtract(BaseModel):
    summary: str = ""
    characters: list[NamedEntity] = Field(default_factory=list)
    locations: list[NamedEntity] = Field(default_factory=list)
    factions: list[NamedEntity] = Field(default_factory=list)
    props: list[NamedEntity] = Field(default_factory=list)
    events: list[dict[str, Any]] = Field(default_factory=list)
    foreshadowing: list[dict[str, Any]] = Field(default_factory=list)
    relationships: list[dict[str, Any]] = Field(default_factory=list)
    visual_cues: list[str] = Field(default_factory=list)
    visual_candidates: list[dict[str, Any]] = Field(default_factory=list)
    voice_cues: list[str] = Field(default_factory=list)
    adaptation_notes: list[str] = Field(default_factory=list)
    quality: ChunkQuality = Field(default_factory=ChunkQuality)
    schema_version: str = "2"


REQUIRED_BIBLE_KEYS = [
    "project_meta", "logline", "worldbuilding", "plot_structure", "characters",
    "character_relations", "locations", "factions", "props", "timeline",
    "foreshadowing", "adaptation_notes", "visual_style", "character_visuals",
    "voice_bible", "production_constraints",
]
