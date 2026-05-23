from typing import Literal

from pydantic import BaseModel, Field, field_validator

EvidenceLevel = Literal["low", "moderate", "strong"]


class KnowledgeCard(BaseModel):
    id: str
    topic: str
    title: str
    claim: str
    practical_rule: str
    when_to_use: str
    avoid_advising: str
    evidence_level: EvidenceLevel
    source_name: str
    source_url: str
    tags: list[str] = Field(default_factory=list)
    created_at: str
    updated_at: str
    active: bool

    @field_validator("topic", "title", "claim", "practical_rule", "when_to_use", "avoid_advising", "source_name", "source_url")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Knowledge card text fields must not be empty.")
        return cleaned

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("Knowledge cards must have at least one tag.")
        return cleaned
