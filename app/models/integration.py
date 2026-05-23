from typing import Literal

from pydantic import BaseModel, Field

IntegrationKind = Literal["calendar", "health"]
IntegrationStatus = Literal["connected", "disconnected"]


class IntegrationConnectionRecord(BaseModel):
    id: str
    user_id: str
    kind: IntegrationKind
    provider_name: str
    status: IntegrationStatus
    metadata: dict[str, str] = Field(default_factory=dict)
    created_at: str
    updated_at: str
    disconnected_at: str | None = None


class IntegrationConnectRequest(BaseModel):
    provider_name: str = "mock"


class CalendarEventSummary(BaseModel):
    title: str
    starts_at: str
    ends_at: str
    is_private: bool = False


class HealthSleepSummary(BaseModel):
    id: str | None = None
    user_id: str | None = None
    provider_name: str
    sleep_start: str
    sleep_end: str
    wake_time: str
    sleep_duration_minutes: int
    interruptions: int | None = None
    resting_heart_rate: float | None = None
    sleep_score: float | None = None
    device_derived: bool = True
    raw_summary: dict[str, str | int | float] = Field(default_factory=dict)
    created_at: str | None = None


class IntegrationSummaryResponse(BaseModel):
    connections: list[IntegrationConnectionRecord]
