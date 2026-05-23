from typing import Literal

from pydantic import BaseModel, Field, field_validator

InsightConfidence = Literal["high", "medium", "low"]
InsightStatus = Literal["active", "dismissed", "archived"]
InsightFrequency = Literal["weekly"]


class InsightRecord(BaseModel):
    id: str
    user_id: str
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    confidence: InsightConfidence
    suggested_experiment: str
    related_memory_ids: list[str] = Field(default_factory=list)
    related_message_ids: list[str] = Field(default_factory=list)
    related_knowledge_card_ids: list[str] = Field(default_factory=list)
    status: InsightStatus
    created_at: str
    updated_at: str
    last_shown_at: str | None = None


class InsightCreateRequest(BaseModel):
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    confidence: InsightConfidence
    suggested_experiment: str
    related_memory_ids: list[str] = Field(default_factory=list)
    related_message_ids: list[str] = Field(default_factory=list)
    related_knowledge_card_ids: list[str] = Field(default_factory=list)
    status: InsightStatus = "active"
    last_shown_at: str | None = None

    @field_validator("title", "summary", "suggested_experiment")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Insight text fields must not be empty.")
        return cleaned

    @field_validator("evidence")
    @classmethod
    def validate_evidence(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value if item.strip()]
        if not cleaned:
            raise ValueError("Insights must include at least one evidence item.")
        return cleaned


class InsightUpdateRequest(BaseModel):
    title: str | None = None
    summary: str | None = None
    evidence: list[str] | None = None
    confidence: InsightConfidence | None = None
    suggested_experiment: str | None = None
    related_memory_ids: list[str] | None = None
    related_message_ids: list[str] | None = None
    related_knowledge_card_ids: list[str] | None = None
    status: InsightStatus | None = None
    last_shown_at: str | None = None


class InsightPreferenceRecord(BaseModel):
    user_id: str
    proactive_insights_enabled: bool
    proactive_insight_frequency: InsightFrequency
    last_proactive_insight_at: str | None = None
    insight_min_evidence_threshold: int = Field(ge=1)
    updated_at: str


class InsightPreferenceUpdateRequest(BaseModel):
    proactive_insights_enabled: bool | None = None
    proactive_insight_frequency: InsightFrequency | None = None
    last_proactive_insight_at: str | None = None
    insight_min_evidence_threshold: int | None = Field(default=None, ge=1)


class InsightCandidate(BaseModel):
    title: str
    summary: str
    evidence: list[str] = Field(default_factory=list)
    confidence: InsightConfidence
    suggested_experiment: str

    @field_validator("title", "summary", "suggested_experiment")
    @classmethod
    def validate_candidate_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Insight candidate fields must not be empty.")
        return cleaned

    @field_validator("evidence")
    @classmethod
    def validate_candidate_evidence(cls, value: list[str]) -> list[str]:
        return [item.strip() for item in value if item.strip()]


class InsightGenerationResult(BaseModel):
    should_create_insight: bool
    insights: list[InsightCandidate] = Field(default_factory=list)
    reason_if_none: str = ""


class InsightSummaryResponse(BaseModel):
    insights: list[InsightRecord]
