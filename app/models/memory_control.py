from pydantic import BaseModel, field_validator


DEFAULT_SESSION_ID = "__default__"


class MemorySessionToggleRequest(BaseModel):
    session_id: str

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("session_id must not be empty.")
        return cleaned


class MemorySessionStateRecord(BaseModel):
    user_id: str
    session_id: str
    memory_enabled: bool
    updated_at: str


class AdviceTraceRecord(BaseModel):
    id: str
    user_id: str
    session_id: str
    user_message: str
    assistant_reply: str
    source_memory_ids: list[str]
    knowledge_card_ids: list[str]
    safety_category: str
    created_at: str


class PendingMemoryConfirmationRecord(BaseModel):
    id: str
    user_id: str
    session_id: str
    memory_updates_json: str
    prompt_text: str
    created_at: str
