import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from app.models.reminder import (
    DueReminderPayload,
    DueReminderResponse,
    ReminderCreateRequest,
    ReminderRecord,
    ReminderUpdateRequest,
)
from app.models.settings import QuietHours
from app.repositories.reminder_repository import ReminderRepository


class ReminderService:
    def __init__(self, repository: ReminderRepository, user_id: str) -> None:
        self.repository = repository
        self.user_id = user_id

    def create_reminder(self, request: ReminderCreateRequest) -> ReminderRecord:
        return self.repository.create_reminder(self.user_id, request)

    def list_reminders(self) -> list[ReminderRecord]:
        return self.repository.list_reminders(self.user_id)

    def update_reminder(self, reminder_id: str, patch: ReminderUpdateRequest) -> ReminderRecord:
        return self.repository.update_reminder(reminder_id, self.user_id, patch)

    def delete_reminder(self, reminder_id: str) -> ReminderRecord | None:
        return self.repository.delete_reminder(reminder_id, self.user_id)

    def format_reminders_for_user(self) -> str:
        reminders = self.list_reminders()
        if not reminders:
            return "You do not have any reminders set right now."
        lines = ["Here are your reminders:"]
        for reminder in reminders:
            status = "on" if reminder.active else "off"
            lines.append(
                f"- {reminder.title} at {reminder.scheduled_time} ({reminder.timezone}, {status})"
            )
        return "\n".join(lines)

    def parse_reminder_request(self, user_message: str, timezone: str) -> ReminderCreateRequest | None:
        lowered = user_message.strip().lower()
        time_match = re.search(r"at\s+(\d{1,2}:\d{2})", lowered)
        if lowered.startswith("remind me to start winding down") and time_match:
            local_time = self._next_local_time(time_match.group(1), timezone)
            return ReminderCreateRequest(
                type="evening_wind_down",
                title="Wind down reminder",
                message="Start winding down now.",
                scheduled_time=local_time,
                timezone=timezone,
                recurrence_rule="DAILY",
                source="user_request",
            )
        if lowered.startswith("remind me tomorrow morning"):
            local_time = self._tomorrow_morning(timezone)
            message = user_message.split("to", 1)[1].strip() if "to" in user_message.lower() else "Follow your sleep experiment."
            return ReminderCreateRequest(
                type="experiment_followup",
                title="Morning reminder",
                message=message.rstrip(".") + ".",
                scheduled_time=local_time,
                timezone=timezone,
                recurrence_rule=None,
                source="user_request",
            )
        return None

    def send_due_reminders(
        self,
        quiet_hours: QuietHours,
        now_utc: datetime | None = None,
    ) -> DueReminderResponse:
        now = now_utc or datetime.now(UTC)
        due_payloads: list[DueReminderPayload] = []
        for reminder in self.repository.list_reminders(self.user_id, active_only=True):
            scheduled = datetime.fromisoformat(reminder.scheduled_time)
            if scheduled > now:
                continue
            local_now = now.astimezone(ZoneInfo(reminder.timezone))
            if self._is_in_quiet_hours(local_now, quiet_hours):
                deferred = self._end_of_quiet_hours(local_now, quiet_hours).astimezone(UTC)
                self.update_reminder(
                    reminder.id,
                    ReminderUpdateRequest(scheduled_time=deferred.replace(microsecond=0).isoformat()),
                )
                due_payloads.append(
                    DueReminderPayload(
                        reminder_id=reminder.id,
                        title=reminder.title,
                        message=reminder.message,
                        scheduled_time=deferred.replace(microsecond=0).isoformat(),
                        timezone=reminder.timezone,
                        action="defer",
                    )
                )
                continue
            if reminder.recurrence_rule == "DAILY":
                next_time = scheduled + timedelta(days=1)
                self.update_reminder(
                    reminder.id,
                    ReminderUpdateRequest(
                        scheduled_time=next_time.replace(microsecond=0).isoformat(),
                        last_sent_at=now.replace(microsecond=0).isoformat(),
                    ),
                )
                action = "reschedule"
            else:
                self.update_reminder(
                    reminder.id,
                    ReminderUpdateRequest(
                        active=False,
                        last_sent_at=now.replace(microsecond=0).isoformat(),
                    ),
                )
                action = "deactivate"
            due_payloads.append(
                DueReminderPayload(
                    reminder_id=reminder.id,
                    title=reminder.title,
                    message=reminder.message,
                    scheduled_time=reminder.scheduled_time,
                    timezone=reminder.timezone,
                    action=action,
                )
            )
        return DueReminderResponse(reminders=due_payloads)

    @staticmethod
    def _next_local_time(time_text: str, timezone: str) -> str:
        hour, minute = [int(part) for part in time_text.split(":")]
        zone = ZoneInfo(timezone)
        now = datetime.now(zone)
        candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if candidate <= now:
            candidate += timedelta(days=1)
        return candidate.astimezone(UTC).replace(microsecond=0).isoformat()

    @staticmethod
    def _tomorrow_morning(timezone: str) -> str:
        zone = ZoneInfo(timezone)
        now = datetime.now(zone)
        candidate = (now + timedelta(days=1)).replace(hour=9, minute=0, second=0, microsecond=0)
        return candidate.astimezone(UTC).replace(microsecond=0).isoformat()

    @staticmethod
    def _is_in_quiet_hours(local_now: datetime, quiet_hours: QuietHours) -> bool:
        now_minutes = local_now.hour * 60 + local_now.minute
        start_hour, start_minute = [int(part) for part in quiet_hours.start.split(":")]
        end_hour, end_minute = [int(part) for part in quiet_hours.end.split(":")]
        start_minutes = start_hour * 60 + start_minute
        end_minutes = end_hour * 60 + end_minute
        if start_minutes <= end_minutes:
            return start_minutes <= now_minutes < end_minutes
        return now_minutes >= start_minutes or now_minutes < end_minutes

    @staticmethod
    def _end_of_quiet_hours(local_now: datetime, quiet_hours: QuietHours) -> datetime:
        end_hour, end_minute = [int(part) for part in quiet_hours.end.split(":")]
        candidate = local_now.replace(hour=end_hour, minute=end_minute, second=0, microsecond=0)
        if candidate <= local_now:
            candidate += timedelta(days=1)
        return candidate
