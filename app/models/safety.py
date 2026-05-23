from typing import Literal

from pydantic import BaseModel, Field

SafetyCategory = Literal["A", "B", "C", "D"]
SafetySeverity = Literal["mild_concern", "medical_red_flag", "urgent_safety_risk"]


class SafetyRedFlag(BaseModel):
    type: str
    evidence: str
    severity: SafetySeverity


class SafetyClassification(BaseModel):
    category: SafetyCategory
    red_flags: list[SafetyRedFlag] = Field(default_factory=list)
    should_recommend_professional_help: bool
    should_prioritize_immediate_safety: bool
    assistant_guidance: str
