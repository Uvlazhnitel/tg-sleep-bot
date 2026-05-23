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
    is_archived: bool


class MemoryCreateRequest(BaseModel):
    type: MemoryType
    content: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str = "manual"

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
