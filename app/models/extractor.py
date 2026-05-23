from typing import Literal

from pydantic import BaseModel, Field

from app.models.memory import MemoryType, RelationType


class MemoryUpdateProposal(BaseModel):
    action: Literal["create", "update", "archive", "none"]
    type: MemoryType | None = None
    content: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    sensitivity: Literal["normal", "sensitive", "crisis"] = "normal"
    should_ask_user_before_saving: bool = False
    reason: str
    target_memory_id: str | None = None
    related_memory_id: str | None = None
    relation_type: RelationType | None = None


class IgnoredMemoryCandidate(BaseModel):
    content: str
    reason: str


class MemoryExtractionResult(BaseModel):
    memory_updates: list[MemoryUpdateProposal]
    skip_memory: bool = False
    ignored: list[IgnoredMemoryCandidate] = Field(default_factory=list)
