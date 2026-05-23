import json
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, field_validator

FeatureName = Literal["reminders", "calendar", "health_data", "timezone_travel", "voice_mode"]


class QuietHours(BaseModel):
    start: str = "22:30"
    end: str = "08:30"

    @field_validator("start", "end")
    @classmethod
    def validate_time_format(cls, value: str) -> str:
        cleaned = value.strip()
        parts = cleaned.split(":")
        if len(parts) != 2:
            raise ValueError("Time must be in HH:MM format.")
        hour, minute = parts
        if not (hour.isdigit() and minute.isdigit()):
            raise ValueError("Time must be in HH:MM format.")
        if not (0 <= int(hour) <= 23 and 0 <= int(minute) <= 59):
            raise ValueError("Time must be valid.")
        return f"{int(hour):02d}:{int(minute):02d}"


class UserSettingsRecord(BaseModel):
    user_id: str
    timezone: str
    reminders_enabled: bool
    calendar_enabled: bool
    health_data_enabled: bool
    voice_mode: bool
    private_mode_default: bool
    proactive_insights_enabled: bool
    feature_flags: dict[str, bool] = Field(default_factory=dict)
    notification_quiet_hours: QuietHours = Field(default_factory=QuietHours)
    goal_timezone_override: str | None = None
    goal_timezone_override_until: str | None = None
    updated_at: str

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        cleaned = value.strip()
        try:
            ZoneInfo(cleaned)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Invalid timezone.") from exc
        return cleaned

    @field_validator("goal_timezone_override")
    @classmethod
    def validate_goal_timezone_override(cls, value: str | None) -> str | None:
        if value is None:
            return value
        cleaned = value.strip()
        try:
            ZoneInfo(cleaned)
        except ZoneInfoNotFoundError as exc:
            raise ValueError("Invalid timezone override.") from exc
        return cleaned


class UserSettingsUpdateRequest(BaseModel):
    timezone: str | None = None
    reminders_enabled: bool | None = None
    calendar_enabled: bool | None = None
    health_data_enabled: bool | None = None
    voice_mode: bool | None = None
    private_mode_default: bool | None = None
    proactive_insights_enabled: bool | None = None
    feature_flags: dict[str, bool] | None = None
    notification_quiet_hours: QuietHours | None = None
    goal_timezone_override: str | None = None
    goal_timezone_override_until: str | None = None

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return UserSettingsRecord.validate_timezone(value)

    @field_validator("goal_timezone_override")
    @classmethod
    def validate_goal_timezone_override(cls, value: str | None) -> str | None:
        if value is None:
            return value
        return UserSettingsRecord.validate_goal_timezone_override(value)


class FeatureListResponse(BaseModel):
    enabled_features: list[FeatureName]


def encode_feature_flags(flags: dict[str, bool]) -> str:
    return json.dumps(flags, sort_keys=True)
