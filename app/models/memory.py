from typing import Literal

from pydantic import BaseModel, Field, field_validator

MemoryType = Literal[
    "fixed_goal",
    "preference",
    "pattern",
    "hypothesis",
    "worked_before",
    "did_not_work",
]
RelationType = Literal["supports", "contradicts", "updates"]
MemoryFeedback = Literal["confirmed", "wrong", "not_relevant", "helped", "did_not_help"]


class MemoryRecord(BaseModel):
    id: str
    user_id: str
    type: MemoryType
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str
    created_at: str
    updated_at: str
    last_used_at: str | None = None
    evidence_count: int = Field(default=1, ge=0)
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    last_confirmed_at: str | None = None
    related_memory_id: str | None = None
    relation_type: RelationType | None = None
    is_archived: bool


class MemoryCreateRequest(BaseModel):
    type: MemoryType
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = "manual"
    evidence_count: int = Field(default=1, ge=0)
    positive_count: int = Field(default=0, ge=0)
    negative_count: int = Field(default=0, ge=0)
    last_confirmed_at: str | None = None
    related_memory_id: str | None = None
    relation_type: RelationType | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Memory content must not be empty.")
        return cleaned


class MemoryUpdateRequest(BaseModel):
    content: str | None = None
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    source: str | None = None
    evidence_count: int | None = Field(default=None, ge=0)
    positive_count: int | None = Field(default=None, ge=0)
    negative_count: int | None = Field(default=None, ge=0)
    last_confirmed_at: str | None = None
    related_memory_id: str | None = None
    relation_type: RelationType | None = None
    is_archived: bool | None = None

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Memory content must not be empty.")
        return cleaned


class MemorySummaryResponse(BaseModel):
    memories: list[MemoryRecord]


class MemoryFeedbackRequest(BaseModel):
    memory_id: str
    feedback: MemoryFeedback
