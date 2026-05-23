from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.models.integration import CalendarEventSummary, HealthSleepSummary, IntegrationConnectionRecord
from app.repositories.integration_repository import IntegrationRepository


class CalendarProvider(Protocol):
    def get_upcoming_events(self, user_id: str, time_range_hours: int) -> list[CalendarEventSummary]: ...
    def get_next_morning_commitments(self, user_id: str) -> list[CalendarEventSummary]: ...
    def disconnect_calendar(self, user_id: str) -> None: ...


class HealthDataProvider(Protocol):
    def get_recent_sleep_summaries(self, user_id: str, days: int) -> list[HealthSleepSummary]: ...
    def get_last_night_sleep(self, user_id: str) -> HealthSleepSummary | None: ...
    def disconnect_health_provider(self, user_id: str) -> None: ...
    def delete_user_data(self, user_id: str) -> None: ...


@dataclass
class MockCalendarProvider:
    timezone: str

    def get_upcoming_events(self, user_id: str, time_range_hours: int) -> list[CalendarEventSummary]:
        del user_id
        zone = ZoneInfo(self.timezone)
        start = datetime.now(zone).replace(minute=0, second=0, microsecond=0) + timedelta(hours=4)
        end = start + timedelta(hours=1)
        return [
            CalendarEventSummary(
                title="Private event",
                starts_at=start.astimezone(UTC).replace(microsecond=0).isoformat(),
                ends_at=end.astimezone(UTC).replace(microsecond=0).isoformat(),
                is_private=True,
            )
        ]

    def get_next_morning_commitments(self, user_id: str) -> list[CalendarEventSummary]:
        return self.get_upcoming_events(user_id, 24)

    def disconnect_calendar(self, user_id: str) -> None:
        del user_id


@dataclass
class MockHealthDataProvider:
    timezone: str

    def get_recent_sleep_summaries(self, user_id: str, days: int) -> list[HealthSleepSummary]:
        del user_id, days
        return [self._build_summary()]

    def get_last_night_sleep(self, user_id: str) -> HealthSleepSummary | None:
        del user_id
        return self._build_summary()

    def disconnect_health_provider(self, user_id: str) -> None:
        del user_id

    def delete_user_data(self, user_id: str) -> None:
        del user_id

    def _build_summary(self) -> HealthSleepSummary:
        zone = ZoneInfo(self.timezone)
        wake = datetime.now(zone).replace(hour=8, minute=52, second=0, microsecond=0)
        sleep_start = wake - timedelta(hours=7, minutes=12)
        return HealthSleepSummary(
            provider_name="mock",
            sleep_start=sleep_start.astimezone(UTC).replace(microsecond=0).isoformat(),
            sleep_end=wake.astimezone(UTC).replace(microsecond=0).isoformat(),
            wake_time=wake.astimezone(UTC).replace(microsecond=0).isoformat(),
            sleep_duration_minutes=432,
            interruptions=2,
            resting_heart_rate=58.0,
            sleep_score=78.0,
            device_derived=True,
            raw_summary={"quality": "approximate"},
        )


class CalendarService:
    def __init__(self, repository: IntegrationRepository, user_id: str) -> None:
        self.repository = repository
        self.user_id = user_id

    def _provider(self, timezone: str) -> CalendarProvider:
        return MockCalendarProvider(timezone)

    def connect(self, provider_name: str) -> IntegrationConnectionRecord:
        return self.repository.connect(self.user_id, "calendar", provider_name, {"scope": "minimal"})

    def disconnect(self) -> IntegrationConnectionRecord | None:
        connection = self.repository.disconnect(self.user_id, "calendar")
        self._provider("UTC").disconnect_calendar(self.user_id)
        return connection

    def list_connections(self) -> list[IntegrationConnectionRecord]:
        return self.repository.list_connections(self.user_id, "calendar")

    def get_relevant_context(self, timezone: str) -> str | None:
        connection = self.repository.get_active_connection(self.user_id, "calendar")
        if connection is None:
            return None
        events = self._provider(timezone).get_next_morning_commitments(self.user_id)
        if not events:
            return None
        return "Calendar context: you have at least one morning commitment, so timing advice should stay practical."

    def delete_data(self) -> str:
        return "No calendar event data is stored locally, so there is nothing additional to delete."


class HealthDataService:
    def __init__(self, repository: IntegrationRepository, user_id: str) -> None:
        self.repository = repository
        self.user_id = user_id

    def _provider(self, timezone: str) -> HealthDataProvider:
        return MockHealthDataProvider(timezone)

    def connect(self, provider_name: str, timezone: str) -> IntegrationConnectionRecord:
        connection = self.repository.connect(self.user_id, "health", provider_name, {"scope": "sleep_summary"})
        summary = self._provider(timezone).get_last_night_sleep(self.user_id)
        if summary is not None:
            self.repository.save_health_summary(self.user_id, summary)
        return connection

    def disconnect(self) -> IntegrationConnectionRecord | None:
        connection = self.repository.disconnect(self.user_id, "health")
        self._provider("UTC").disconnect_health_provider(self.user_id)
        return connection

    def list_connections(self) -> list[IntegrationConnectionRecord]:
        return self.repository.list_connections(self.user_id, "health")

    def get_relevant_context(self, timezone: str) -> str | None:
        connection = self.repository.get_active_connection(self.user_id, "health")
        if connection is None:
            return None
        summaries = self.repository.list_health_summaries(self.user_id, connection.provider_name)
        if not summaries:
            summary = self._provider(timezone).get_last_night_sleep(self.user_id)
            if summary is not None:
                saved = self.repository.save_health_summary(self.user_id, summary)
                summaries = [saved]
        if not summaries:
            return None
        latest = summaries[0]
        return (
            "Health data context: your wearable estimate suggests about "
            f"{latest.sleep_duration_minutes // 60}h {latest.sleep_duration_minutes % 60}m last night, "
            "but device data is approximate."
        )

    def delete_data(self, provider_name: str | None = None) -> int:
        if provider_name:
            self._provider("UTC").delete_user_data(self.user_id)
        return self.repository.delete_health_data(self.user_id, provider_name)
