from typing import Literal

from pydantic import BaseModel, Field, field_validator


class HistoryMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("History content must not be empty.")
        return cleaned


class ChatRequest(BaseModel):
    message: str
    history: list[HistoryMessage] = Field(default_factory=list)
    include_debug: bool = False

    @field_validator("message")
    @classmethod
    def validate_message(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Message must not be empty.")
        return cleaned


class ChatDebugMetadata(BaseModel):
    memory_ids: list[str] = Field(default_factory=list)
    knowledge_card_ids: list[str] = Field(default_factory=list)
    personalization_context: str | None = None
    safety_category: str | None = None
    safety_red_flag_types: list[str] = Field(default_factory=list)
    should_prioritize_immediate_safety: bool | None = None


class ChatResponse(BaseModel):
    reply: str
    debug: ChatDebugMetadata | None = None


class HealthResponse(BaseModel):
    status: Literal["ok"]
