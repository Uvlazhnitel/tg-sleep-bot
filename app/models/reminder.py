from typing import Literal

from pydantic import BaseModel, Field, field_validator

ReminderType = Literal[
    "evening_wind_down",
    "morning_wake_support",
    "experiment_followup",
    "custom_sleep_reminder",
]


class ReminderRecord(BaseModel):
    id: str
    user_id: str
    type: ReminderType
    title: str
    message: str
    scheduled_time: str
    timezone: str
    recurrence_rule: str | None = None
    active: bool
    source: str
    last_sent_at: str | None = None
    created_at: str
    updated_at: str


class ReminderCreateRequest(BaseModel):
    type: ReminderType
    title: str
    message: str
    scheduled_time: str
    timezone: str
    recurrence_rule: str | None = None
    active: bool = True
    source: str = "user_request"

    @field_validator("title", "message", "scheduled_time", "timezone")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("Reminder fields must not be empty.")
        return cleaned


class ReminderUpdateRequest(BaseModel):
    title: str | None = None
    message: str | None = None
    scheduled_time: str | None = None
    timezone: str | None = None
    recurrence_rule: str | None = None
    active: bool | None = None
    last_sent_at: str | None = None


class ReminderSummaryResponse(BaseModel):
    reminders: list[ReminderRecord]


class DueReminderPayload(BaseModel):
    reminder_id: str
    title: str
    message: str
    scheduled_time: str
    timezone: str
    action: Literal["send", "defer", "deactivate", "reschedule"]


class DueReminderResponse(BaseModel):
    reminders: list[DueReminderPayload] = Field(default_factory=list)
